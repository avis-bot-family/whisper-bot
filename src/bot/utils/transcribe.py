import httpx
from loguru import logger

from bot.settings import settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _client


async def transcribe_audio(
    file_path: str,
    model: str = "medium",
    language: str = "Russian",
) -> dict:
    """Отправляет запрос на транскрибацию в transcribe-worker.

    Возвращает словарь с ключами:
    - "text": полный текст транскрибации
    - "segments": список сегментов с таймкодами
    """
    url = f"{settings.transcribe.WHISPER_SERVICE_URL}/transcribe"
    payload = {"file_path": file_path, "model": model, "language": language}

    logger.info(f"Запрос транскрибации: {url} file_path={file_path}")
    client = _get_client()
    response = await client.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    logger.info(f"Транскрибация завершена. Сегментов: {len(result.get('segments', []))}")
    return result
