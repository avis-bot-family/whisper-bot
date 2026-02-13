"""Модуль для оптимального скачивания больших файлов из Telegram."""

import asyncio
import os
import time
from collections.abc import Awaitable
from typing import Callable, Optional

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import File
from loguru import logger


class FileDownloadError(Exception):
    """Исключение при ошибке скачивания файла."""

    pass


async def download_file_optimized(
    bot: Bot,
    file_info: File,
    destination_path: str,
    chunk_size: int = 128 * 1024,  # 128 KB по умолчанию для лучшей производительности
    max_retries: int = 3,
    retry_delay: float = 2.0,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    async_progress_callback: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Оптимально скачивает файл из Telegram с поддержкой больших файлов.

    Использует потоковое скачивание с chunked download для эффективной работы
    с большими файлами. Поддерживает повторные попытки при ошибках сети.

    Args:
        bot: Экземпляр бота для доступа к API Telegram
        file_info: Информация о файле из Telegram API
        destination_path: Путь для сохранения файла
        chunk_size: Размер чанка для скачивания в байтах (по умолчанию 128 KB)
        max_retries: Максимальное количество повторных попыток при ошибках
        retry_delay: Задержка между повторными попытками в секундах
        progress_callback: Опциональный синхронный callback для отслеживания прогресса
                          (получено_байт, всего_байт)
        async_progress_callback: Опциональный асинхронный callback для отслеживания прогресса
                                (получено_байт, всего_байт)

    Returns:
        Путь к скачанному файлу

    Raises:
        FileDownloadError: При ошибке скачивания файла
        TelegramBadRequest: При ошибке Telegram API
    """
    if not file_info.file_path:
        raise FileDownloadError("Не удалось получить путь к файлу")

    file_size = getattr(file_info, "file_size", None)

    # Формируем URL файла через API Telegram.
    # Шаблон api.file: https://api.telegram.org/file/bot{token}/{path}
    # Подставляем token и path (file_path из get_file).
    file_url = str(bot.session.api.file).format(token=bot.token, path=file_info.file_path)

    # Создаем директорию для файла, если её нет
    os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)

    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            # Используем aiohttp для потокового скачивания
            # Создаем свою сессию для большего контроля над процессом
            timeout = aiohttp.ClientTimeout(total=3600)  # 1 час для больших файлов
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(file_url) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise FileDownloadError(f"Ошибка при скачивании файла: HTTP {response.status} - {error_text}")

                    # Получаем размер файла из заголовков, если не указан в file_info
                    content_length = response.headers.get("Content-Length")
                    if content_length:
                        total_size = int(content_length)
                    elif file_size:
                        total_size = file_size
                    else:
                        total_size = None

                    # Скачиваем файл по частям (chunked download)
                    downloaded = 0
                    last_progress_update = 0
                    with open(destination_path, "wb") as f:
                        async for chunk in response.content.iter_chunked(chunk_size):
                            f.write(chunk)
                            downloaded += len(chunk)

                            # Вызываем callback для отслеживания прогресса
                            if total_size:
                                # Обновляем прогресс каждые 1% или каждые 5 MB
                                if (
                                    downloaded - last_progress_update >= total_size * 0.01
                                    or downloaded - last_progress_update >= 5 * 1024 * 1024
                                ):
                                    if progress_callback:
                                        progress_callback(downloaded, total_size)
                                    if async_progress_callback:
                                        await async_progress_callback(downloaded, total_size)
                                    last_progress_update = downloaded

                            # Логируем прогресс для больших файлов
                            if total_size and downloaded % (10 * 1024 * 1024) == 0:  # Каждые 10 MB
                                progress_percent = (downloaded / total_size) * 100
                                logger.debug(
                                    f"Прогресс скачивания: {downloaded / (1024 * 1024):.1f} MB / "
                                    f"{total_size / (1024 * 1024):.1f} MB ({progress_percent:.1f}%)"
                                )

                    # Проверяем, что файл скачан полностью
                    if total_size and downloaded != total_size:
                        raise FileDownloadError(f"Файл скачан не полностью: {downloaded} байт из {total_size}")

                    logger.info(f"Файл успешно скачан: {destination_path}, размер: {downloaded / (1024 * 1024):.1f} MB")
                    return destination_path

        except aiohttp.ClientError as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Ошибка сети при скачивании файла (попытка {attempt + 1}/{max_retries}): {e}. "
                    f"Повторная попытка через {retry_delay} сек..."
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Не удалось скачать файл после {max_retries} попыток: {e}")
                raise FileDownloadError(f"Ошибка сети при скачивании файла: {e}") from e

        except TelegramBadRequest as e:
            error_str = str(e).lower()
            if "file is too big" in error_str:
                raise TelegramBadRequest(
                    message=f"Файл слишком большой для загрузки: {e}",
                    method="download_file",
                )
            raise

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                logger.warning(
                    f"Ошибка при скачивании файла (попытка {attempt + 1}/{max_retries}): {e}. "
                    f"Повторная попытка через {retry_delay} сек..."
                )
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"Не удалось скачать файл после {max_retries} попыток: {e}")
                raise FileDownloadError(f"Ошибка при скачивании файла: {e}") from e

    # Если дошли сюда, все попытки исчерпаны
    raise FileDownloadError(f"Не удалось скачать файл после {max_retries} попыток: {last_error}")


async def download_file_with_progress(
    bot: Bot,
    file_info: File,
    destination_path: str,
    status_message: Optional[object] = None,
    update_status_func: Optional[Callable[[object, str], Awaitable[None]]] = None,
    chunk_size: int = 128 * 1024,  # 128 KB для лучшей производительности
) -> str:
    """Скачивает файл с обновлением статуса в Telegram сообщении.

    Args:
        bot: Экземпляр бота для доступа к API Telegram
        file_info: Информация о файле из Telegram API
        destination_path: Путь для сохранения файла
        status_message: Опциональное сообщение для обновления статуса
        update_status_func: Функция для обновления статуса (status_message, text)
        chunk_size: Размер чанка для скачивания в байтах

    Returns:
        Путь к скачанному файлу
    """
    last_progress_percent = -1
    last_update_time = 0.0

    async def async_progress_callback(downloaded: int, total: int) -> None:
        """Асинхронный callback для обновления прогресса скачивания.
        Throttle: не чаще 1 раза в 2 с и не чаще чем каждые 10% — чтобы не упираться в Flood control.
        """
        nonlocal last_progress_percent, last_update_time
        if not (status_message and update_status_func and total):
            return
        progress_percent = (downloaded / total) * 100
        now = time.monotonic()
        # Обновляем при приросте ≥10% или при 100%, и не чаще чем раз в 2 секунды
        pct_ok = progress_percent - last_progress_percent >= 10 or progress_percent >= 99.9
        time_ok = last_update_time == 0 or (now - last_update_time) >= 2.0
        if pct_ok and time_ok:
            downloaded_mb = downloaded / (1024 * 1024)
            total_mb = total / (1024 * 1024)
            status_text = (
                f"📥 <b>Скачиваю файл...</b>\n\n"
                f"📊 <b>Прогресс:</b> {progress_percent:.1f}%\n"
                f"💾 {downloaded_mb:.1f} MB / {total_mb:.1f} MB"
            )
            try:
                await update_status_func(status_message, status_text)
                last_progress_percent = progress_percent
                last_update_time = now
            except Exception as e:
                logger.debug(f"Не удалось обновить статус: {e}")

    return await download_file_optimized(
        bot=bot,
        file_info=file_info,
        destination_path=destination_path,
        chunk_size=chunk_size,
        async_progress_callback=async_progress_callback if (status_message and update_status_func) else None,
    )
