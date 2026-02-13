"""Скачивание файлов по публичным ссылкам Google Drive."""

import asyncio
import os
import re
import time
from collections.abc import Awaitable
from typing import Callable, Optional

import aiohttp
from loguru import logger


# Форматы ссылок: .../file/d/FILE_ID/..., ...?id=FILE_ID, .../open?id=FILE_ID
GOOGLE_DRIVE_LINK_RE = re.compile(
    r"(?:https?://)?drive\.google\.com/file/d/([a-zA-Z0-9_-]+)"
    r"|(?:https?://)?drive\.google\.com/(?:uc\?id=|open\?id=)([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)

DOWNLOAD_URL = "https://docs.google.com/uc"
CHUNK_SIZE = 128 * 1024  # 128 KB


def extract_google_drive_file_id(text: str) -> Optional[str]:
    """Извлекает file_id из текста со ссылкой на Google Drive.

    Поддерживает:
    - https://drive.google.com/file/d/FILE_ID/view?usp=sharing
    - https://drive.google.com/uc?id=FILE_ID
    - https://drive.google.com/open?id=FILE_ID
    """
    if not text or not text.strip():
        return None
    text = text.strip()
    for match in GOOGLE_DRIVE_LINK_RE.finditer(text):
        g1, g2 = match.group(1), match.group(2)
        file_id = g1 or g2
        if file_id:
            return file_id
    return None


async def download_from_google_drive(
    file_id: str,
    destination_path: str,
    status_message: Optional[object] = None,
    update_status_func: Optional[Callable[[object, str], Awaitable[None]]] = None,
    chunk_size: int = CHUNK_SIZE,
    max_retries: int = 3,
) -> str:
    """Скачивает файл с Google Drive по file_id (публичная ссылка).

    Использует docs.google.com/uc?export=download и при необходимости
    подтверждение из cookie download_warning для больших файлов.
    """
    os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
    last_progress_percent = -1
    last_update_time = 0.0

    async def maybe_update_progress(downloaded: int, total: Optional[int]) -> None:
        nonlocal last_progress_percent, last_update_time
        if not (status_message and update_status_func):
            return
        if total and total > 0:
            progress_percent = (downloaded / total) * 100
            now = time.monotonic()
            if (progress_percent - last_progress_percent >= 10 or progress_percent >= 99.9) and (
                last_update_time == 0 or (now - last_update_time) >= 2.0
            ):
                try:
                    status_text = (
                        f"📥 <b>Скачиваю с Google Drive...</b>\n\n"
                        f"📊 <b>Прогресс:</b> {progress_percent:.1f}%\n"
                        f"💾 {downloaded / (1024 * 1024):.1f} MB / {total / (1024 * 1024):.1f} MB"
                    )
                    await update_status_func(status_message, status_text)
                    last_progress_percent = progress_percent
                    last_update_time = now
                except Exception as e:
                    logger.debug(f"Не удалось обновить статус: {e}")
        else:
            if last_update_time == 0 or (time.monotonic() - last_update_time) >= 2.0:
                try:
                    await update_status_func(
                        status_message,
                        f"📥 <b>Скачиваю с Google Drive...</b>\n\n💾 {downloaded / (1024 * 1024):.1f} MB",
                    )
                    last_update_time = time.monotonic()
                except Exception as e:
                    logger.debug(f"Не удалось обновить статус: {e}")

    last_error: Optional[Exception] = None
    timeout = aiohttp.ClientTimeout(total=3600)

    for attempt in range(max_retries):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                params: dict = {"id": file_id, "export": "download", "confirm": "1"}
                async with session.get(DOWNLOAD_URL, params=params) as response:
                    # Для больших файлов Google может вернуть HTML с предупреждением;
                    # в cookie приходит download_warning — делаем второй запрос с confirm=token
                    if response.content_type and "text/html" in response.content_type:
                        body = await response.text()
                        # Пробуем взять confirm из cookie
                        confirm = None
                        for name, value in response.cookies.items():
                            if name.startswith("download_warning"):
                                confirm = value
                                break
                        if not confirm and "download_warning" in body:
                            # Парсим из HTML: name="download_warning" value="..."
                            m = re.search(r'name="download_warning"\s+value="([^"]+)"', body)
                            if m:
                                confirm = m.group(1)
                        if confirm:
                            params["confirm"] = confirm
                            async with session.get(DOWNLOAD_URL, params=params) as resp2:
                                if resp2.status != 200:
                                    raise OSError(f"Google Drive: HTTP {resp2.status}")
                                content_length = resp2.headers.get("Content-Length")
                                total_size = int(content_length) if content_length else None
                                downloaded = 0
                                with open(destination_path, "wb") as f:
                                    async for chunk in resp2.content.iter_chunked(chunk_size):
                                        f.write(chunk)
                                        downloaded += len(chunk)
                                        await maybe_update_progress(downloaded, total_size)
                                if total_size and downloaded != total_size:
                                    raise OSError(f"Скачано {downloaded} из {total_size} байт")
                                logger.info(f"Google Drive: файл скачан {destination_path}, {downloaded} байт")
                                return destination_path
                        # Иначе это страница ошибки (404, нет доступа и т.д.)
                        if "not found" in body.lower() or "404" in body:
                            raise OSError("Файл не найден или ссылка не публичная")
                        raise OSError("Google Drive вернул HTML вместо файла. Проверьте, что ссылка с доступом «все по ссылке».")

                    if response.status != 200:
                        raise OSError(f"Google Drive: HTTP {response.status}")

                    content_length = response.headers.get("Content-Length")
                    total_size = int(content_length) if content_length else None
                    downloaded = 0
                    with open(destination_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)
                            await maybe_update_progress(downloaded, total_size)

                    if total_size and downloaded != total_size:
                        raise OSError(f"Скачано {downloaded} из {total_size} байт")

                    logger.info(f"Google Drive: файл скачан {destination_path}, {downloaded} байт")
                    return destination_path

        except (aiohttp.ClientError, OSError) as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(f"Ошибка при скачивании с Google Drive (попытка {attempt + 1}/{max_retries}): {e}")
                await asyncio.sleep(2.0)
            else:
                raise

    raise OSError(f"Не удалось скачать файл с Google Drive: {last_error}")
