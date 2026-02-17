import asyncio
import orjson
from datetime import datetime
from typing import Awaitable, Union
from uuid import UUID
from functools import wraps
from redis.asyncio.cluster import ClusterNode, RedisCluster
from redis.exceptions import RedisError

from fm_logger_config import fm_get_logger

from app.shared.settings import RedisConfig

logger = fm_get_logger(__name__)


class CacheClientError(RedisError):
    pass


def _apply_prefix(prefix_key: str, kwargs: dict) -> None:
    if kwargs.get('key', ''):
        logger.debug(f"Set prefix '{prefix_key}:' for key {kwargs['key']}")
        kwargs['key'] = prefix_key + ":" + kwargs['key']


def set_redis_prefix(func):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        _apply_prefix(args[0]._redis_prefix, kwargs)
        result = await func(*args, **kwargs)
        logger.debug(f"Response from '{func.__name__}' = {result}")
        return result

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        _apply_prefix(args[0]._redis_prefix, kwargs)
        result = func(*args, **kwargs)
        logger.debug(f"Response from '{func.__name__}' = {result}")
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


class RedisCacheClient:
    def __init__(self, redis_settings: RedisConfig):
        self._redis_settings = redis_settings
        self._redis_prefix = redis_settings.PREFIX
        self._cluster_nodes = []
        self._redis_cluster: RedisCluster | None = None
        for node in self._redis_settings.redis_cluster_nodes:
            set_node = ClusterNode(node.get("host", ""), node.get("port", ""))
            self._cluster_nodes.append(set_node)

    async def init_redis_client(self) -> None:
        if self._redis_cluster is None:
            self._redis_cluster = await self._init_redis_cluster()
            logger.info("Redis cluster connection pool initialized")

    async def _init_redis_cluster(self) -> RedisCluster:
        return RedisCluster(
            startup_nodes=self._cluster_nodes,
            decode_responses=True,
            max_connections=self._redis_settings.MAX_CONNECTIONS,
        )

    async def close_redis_client(self) -> None:
        if not self._redis_cluster:
            return
        cluster = self._redis_cluster
        self._redis_cluster = None
        try:
            await cluster.close()
            logger.info("Redis cluster connection pool closed")
            await asyncio.sleep(0)  # Даём циклу обработать закрытие сокетов
        except Exception as e:
            logger.error(f"Error closing Redis cluster: {e}")
            raise CacheClientError(f"Error closing Redis cluster: {e}")

    @property
    def redis_cluster(self) -> RedisCluster:
        if not self._redis_cluster:
            raise RuntimeError("Redis cluster not initialized")
        return self._redis_cluster

    @set_redis_prefix
    async def set_to_cache(self, *, key: str, value: str | bytes, expire: int = 1, **kwargs) -> None:
        await self.redis_cluster.set(name=key, value=value, ex=expire, **kwargs)

    @set_redis_prefix
    async def set_dict_to_cache(self, *, key: str, value: dict, expire: int = 1) -> Union[Awaitable[str], str]:
        return await self.redis_cluster.hset(name=key, mapping=value)  # type: ignore

    @set_redis_prefix
    async def set_if_not_exists(self, *, key: str, value: str | bytes) -> bool:
        return await self.redis_cluster.setnx(name=key, value=value)

    @set_redis_prefix
    async def set_expire(self, *, key: str, expire: int = 1) -> int:
        return await self.redis_cluster.expire(key, expire)

    @set_redis_prefix
    async def get_from_cache(self, *, key: str, **kwargs) -> str | None:
        value = await self.redis_cluster.get(key)
        if value is None:
            return None
        return value.decode() if isinstance(value, bytes) else value

    @set_redis_prefix
    async def del_from_cache(self, *, key: str, **kwargs) -> None:
        await self.redis_cluster.delete(key)
        return None

    @set_redis_prefix
    async def publish_to_stream(self, stream_key: str, value: dict) -> str:
        """Публикация события в Redis Stream."""
        prepared_value = self._prepare_redis_fields(value)
        stream_task_id = await self.redis_cluster.xadd(
            name=stream_key,
            fields=prepared_value,
            maxlen=self._redis_settings.MAX_STREAM_LENGTH,
            approximate=True,
        )
        return stream_task_id

    def _prepare_redis_fields(self, data: dict) -> dict:
        prepared = {}
        for key, val in data.items():
            if isinstance(val, dict) or isinstance(val, list) or isinstance(val, tuple):
                prepared[key] = orjson.dumps(val).decode('utf-8')
            elif isinstance(val, datetime):
                prepared[key] = val.isoformat()
            elif isinstance(val, UUID):
                prepared[key] = str(val)
            else:
                prepared[key] = val
        return prepared

    @set_redis_prefix
    async def create_consumer_group(self, stream_key: str, group_name: str, start_id: str = "$") -> bool:
        """Создает consumer group для Redis Stream. start_id="$" означает чтение только новых сообщений."""
        try:
            await self.redis_cluster.xgroup_create(
                name=stream_key,
                groupname=group_name,
                id=start_id,
                mkstream=True,
            )
            logger.info(f"Consumer group '{group_name}' created for stream '{stream_key}'")
            return True
        except Exception as e:
            error_str = str(e)
            if "BUSYGROUP" in error_str:
                logger.debug(f"Consumer group '{group_name}' already exists for stream '{stream_key}'")
                return True
            logger.error(f"Error creating consumer group '{group_name}' for stream '{stream_key}': {e}", exc_info=True)
            return False

    @set_redis_prefix
    async def read_stream_events(self, stream_key: str, group_name: str, consumer_name: str) -> list:
        """Читает события из Stream с помощью consumer group."""
        try:
            response = await self.redis_cluster.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                streams={stream_key: self._redis_settings.LAST_ID},
                count=self._redis_settings.BATCH_SIZE,
                block=self._redis_settings.BLOCK_MS,
                noack=False,
            )

            if not response:
                return []

            messages = response[0][1] if response else []

            logger.debug(f"Read {len(messages)} messages from stream '{stream_key}'")
            return messages

        except Exception as e:
            logger.error(f"Error reading from stream '{stream_key}': {e}")
            return []

    @set_redis_prefix
    async def ack_message(self, stream_key: str, group_name: str, message_id: str) -> int:
        """Подтверждает обработку сообщения из Stream."""
        return await self.redis_cluster.xack(stream_key, group_name, message_id)

    @set_redis_prefix
    async def get_stream_event_by_id(self, stream_key: str, event_id: str) -> dict | None:
        """Получает событие из Stream по id."""
        try:
            entries = await self.redis_cluster.xrange(stream_key, event_id, event_id, count=1)
            if not entries:
                return None
            return dict(entries[0][1])
        except Exception as e:
            logger.warning("Error reading event by id from stream %s: %s", stream_key, e)
            return None
