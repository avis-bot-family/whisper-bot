import asyncio

from types import TracebackType
from typing import Any, Sequence, Union, Iterable, Literal, Optional, Type
from threading import RLock
from collections import deque

from clickhouse_connect import get_async_client
from clickhouse_connect.driver.asyncclient import AsyncClient
from clickhouse_connect.driver import httputil

from fm_logger_config import fm_get_logger

from app.shared.settings import ClickHouseConfig


logger = fm_get_logger(__name__)


class ClickHouseClient:
    def __init__(self, clickhouse_config: ClickHouseConfig):
        self._clickhouse_config = clickhouse_config
        self._async_clickhouse_client: AsyncClient | None = None

        # Batch configuration
        self._batch_size = self._clickhouse_config.BATCH_SIZE
        self._flush_interval = self._clickhouse_config.FLUSH_INTERVAL

        max_memory_items = self._batch_size * 2
        self._current_batch: deque = deque(maxlen=max_memory_items)

        self._lock = RLock()
        self._last_flush: float | None = None
        self._is_running = False
        self._worker_task = None
        self._loop = None

    async def __aenter__(self):
        await self.init_clickhouse_client()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]] = None,
        exc_value: Optional[BaseException] = None,
        traceback: Optional[TracebackType] = None,
    ) -> None:
        await self.close_clickhouse_client()

    async def init_clickhouse_client(self) -> None:
        if self._async_clickhouse_client is None:
            self._async_clickhouse_client = await self._init_clickhouse_async_client()
            logger.info("ClickHouse client initialized")

    async def _init_clickhouse_async_client(self) -> AsyncClient:
        pool_mgr = httputil.get_pool_manager(
            maxsize=self._clickhouse_config.MAX_CONNECTIONS,
            num_pools=self._clickhouse_config.NUM_POOLS,
        )

        return await get_async_client(
            dsn=self._clickhouse_config.clickhouse_uri,
            compress=self._clickhouse_config.COMPRESS,
            connect_timeout=self._clickhouse_config.CONNECT_TIMEOUT,
            send_receive_timeout=self._clickhouse_config.READ_TIMEOUT,
            pool_mgr=pool_mgr,
        )

    async def close_clickhouse_client(self) -> None:
        if self._async_clickhouse_client:
            try:
                await self._async_clickhouse_client.close()
            except Exception as e:
                logger.error(f"Error closing ClickHouse client: {e}")
            logger.info("ClickHouse client closed")
            self._async_clickhouse_client = None

    @property
    def async_clickhouse_client(self) -> AsyncClient:
        if not self._async_clickhouse_client:
            raise RuntimeError("ClickHouse client not initialized")
        return self._async_clickhouse_client

    async def insert(
        self, table_name: str, data: Sequence[Sequence[Any]], column_names: Union[str, Iterable[str]] = '*'
    ) -> None:
        await self.async_clickhouse_client.insert(table_name, data, column_names=column_names)

    async def query(self, query: str, parameters: dict[Any, Any] | None = None):
        return await self.async_clickhouse_client.query(query, parameters=parameters)

    def start_batch_worker(self):
        if self._is_running:
            return
        self._is_running = True
        try:
            self._loop = asyncio.get_running_loop()
            self._worker_task = self._loop.create_task(self._batch_worker())
            logger.info("Batch worker task started")
        except RuntimeError:
            logger.error("Batch worker task not started")

    def stop_batch_worker(self):
        if self._is_running:
            self._is_running = False

            if self._worker_task and not self._worker_task.done():
                self._worker_task.cancel()
                try:
                    if self._loop and self._loop.is_running():
                        self._loop.create_task(self._flush_batch())
                    else:
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            loop.run_until_complete(self._flush_batch())
                            loop.close()
                        except Exception as flush_error:
                            logger.error(f"Error during final flush: {flush_error}")
                except Exception as e:
                    logger.error(f"Error during final flush: {e}")
            logger.info("Batch worker stopped")

    async def _get_current_time(self) -> float:
        return asyncio.get_running_loop().time()

    async def _batch_worker(self):
        while self._is_running:
            try:
                current_time = await self._get_current_time()
                if self._last_flush is None:
                    self._last_flush = current_time

                # Проверяем, нужно ли выполнить flush по времени
                time_diff = current_time - self._last_flush
                should_flush_by_time = time_diff >= self._flush_interval
                if should_flush_by_time and len(self._current_batch) > 0:
                    await self._flush_batch('time')

                # Проверяем, нужно ли выполнить flush по размеру batch
                if len(self._current_batch) >= self._batch_size:
                    await self._flush_batch('size')

                await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                logger.info("Batch worker was cancelled")
                break
            except Exception as e:
                logger.error(f"Error in batch worker: {e}")
                await asyncio.sleep(1)

    async def _flush_batch(self, log_action: Literal['force', 'time', 'size'] = 'time'):
        logger.warning(f"Start flush batch with action: {log_action}")

        batch_to_flush = []
        with self._lock:
            if self._current_batch:
                batch_to_flush = list(self._current_batch)
                self._current_batch.clear()

        if not batch_to_flush:
            return

        self._last_flush = await self._get_current_time()
        try:
            table_batches: dict[str, dict[str, Any]] = {}
            for table_name, data, column_names in batch_to_flush:
                if table_name not in table_batches:
                    table_batches[table_name] = {'data': [], 'column_names': column_names}
                table_batches[table_name]['data'].extend(data)

            for table_name, batch_info in table_batches.items():
                await self.async_clickhouse_client.insert(
                    table_name, batch_info['data'], column_names=batch_info['column_names']
                )

            logger.warning(f"Successfully flushed batch: {len(batch_to_flush)} operations")
        except Exception as e:
            logger.error(f"Error during batch flush: {e}")
            with self._lock:
                self._current_batch.extend(batch_to_flush)

    def add_to_batch(
        self,
        table_name: str,
        data: Sequence[Sequence[Any]],
        column_names: Union[str, Iterable[str]] = '*',
    ):
        if not data:
            logger.info("Empty data provided to add_to_batch")
            return

        batch_item = (table_name, data, column_names)
        with self._lock:
            self._current_batch.append(batch_item)

        if not self._is_running:
            self.start_batch_worker()

    async def bulk_insert(
        self,
        table_name: str,
        data: Sequence[Sequence[Any]],
        column_names: Union[str, Iterable[str]] = '*',
        use_batch: bool = True,
    ) -> None:
        if use_batch:
            self.add_to_batch(table_name, data, column_names)
        else:
            await self.async_clickhouse_client.insert(table_name, data, column_names=column_names)

    def force_flush(self):
        try:
            loop = asyncio.get_running_loop()
            # Если мы в running loop, создаем task
            task = loop.create_task(self._flush_batch('force'))
            return task
        except RuntimeError:
            # Если нет running loop, создаем новый
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(self._flush_batch('force'))
                return result
            finally:
                loop.close()

    async def force_flush_async(self):
        await self._flush_batch('force')
