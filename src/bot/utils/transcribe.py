import asyncio

import torch
import whisper
from loguru import logger


def _transcribe_audio_sync(
    file_path: str,
    model: str = "medium",
    language: str = "Russian",
    device: str = "cpu",
) -> dict:
    """Синхронная версия транскрибации для использования в отдельном потоке.

    Возвращает словарь с ключами:
    - "text": полный текст транскрибации
    - "segments": список сегментов с таймкодами
    """
    try:
        logger.info(f"Начинаю транскрибацию файла: {file_path}")
        logger.info(f"Модель: {model}, Язык: {language}, Устройство: {device}")

        # Очистка памяти CUDA перед загрузкой модели
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.info("Очищен кеш CUDA")

        # Определяем устройство
        if device == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA недоступна, используется CPU")
            device = "cpu"

        model_obj = whisper.load_model(model, device=device)
        result = model_obj.transcribe(
            file_path,
            task="transcribe",
            language=language,
        )

        transcribed_text = result["text"].strip()
        segments = result.get("segments", [])
        logger.info(f"Транскрибация завершена успешно. Сегментов: {len(segments)}")

        # Очистка памяти после транскрибации
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
            del model_obj
            torch.cuda.empty_cache()

        return {
            "text": transcribed_text,
            "segments": segments,
        }
    except Exception as e:
        logger.error(f"Ошибка при транскрибации: {e}")
        # Очистка памяти в случае ошибки
        if device == "cuda" and torch.cuda.is_available():
            torch.cuda.empty_cache()
        raise


async def transcribe_audio(
    file_path: str,
    model: str = "medium",
    language: str = "Russian",
    device: str = "cpu",
) -> dict:
    """Запускает транскрибацию аудио файла через whisper в отдельном потоке.

    Возвращает словарь с ключами:
    - "text": полный текст транскрибации
    - "segments": список сегментов с таймкодами
    """
    return await asyncio.to_thread(
        _transcribe_audio_sync,
        file_path,
        model,
        language,
        device,
    )
