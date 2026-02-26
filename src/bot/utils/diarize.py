"""HTTP-клиент для транскрибации с диаризацией через transcribe-worker."""

from __future__ import annotations

import httpx
from loguru import logger

from bot.settings import settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0))
    return _client


async def transcribe_with_diarization(
    file_path: str,
    *,
    model: str = "small",
    language: str = "Russian",
    hf_token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Отправляет запрос на транскрибацию с диаризацией в transcribe-worker.

    Возвращает словарь:
    - "text": полный текст
    - "segments": [{"start", "end", "text", "speaker"}, ...]
    """
    url = f"{settings.transcribe.WHISPER_SERVICE_URL}/transcribe-diarize"
    payload: dict = {
        "file_path": file_path,
        "model": model,
        "language": language,
    }
    if hf_token:
        payload["hf_token"] = hf_token
    if num_speakers is not None:
        payload["num_speakers"] = num_speakers
    if min_speakers is not None:
        payload["min_speakers"] = min_speakers
    if max_speakers is not None:
        payload["max_speakers"] = max_speakers

    logger.info(f"Запрос диаризации: {url} file_path={file_path}")
    client = _get_client()
    response = await client.post(url, json=payload)
    response.raise_for_status()
    result = response.json()
    logger.info(f"Диаризация завершена. Сегментов: {len(result.get('segments', []))}")
    return result
