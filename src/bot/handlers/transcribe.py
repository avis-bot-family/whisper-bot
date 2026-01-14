import os
import tempfile

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from loguru import logger

from bot.enums.file_formats import AudioFormat, FileType, VideoFormat
from bot.settings import Settings
from bot.utils.transcribe import transcribe_audio

settings = Settings()

router = Router(name="transcribe")

# Максимальная длина сообщения в Telegram (с запасом для HTML-тегов)
# Telegram лимит: 4096 символов, но с HTML-тегами лучше использовать меньше
MAX_MESSAGE_LENGTH = 3500


def split_long_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Разбивает длинное сообщение на части, не превышающие лимит."""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    current_part = ""
    
    # Разбиваем по строкам, чтобы не разрывать слова
    lines = text.split("\n")
    
    for line in lines:
        # Если одна строка слишком длинная, разбиваем её по словам
        if len(line) > max_length:
            words = line.split(" ")
            for word in words:
                if len(current_part) + len(word) + 1 > max_length:
                    if current_part:
                        parts.append(current_part.strip())
                        current_part = ""
                current_part += word + " "
        else:
            # Проверяем, поместится ли строка в текущую часть
            if len(current_part) + len(line) + 1 > max_length:
                if current_part:
                    parts.append(current_part.strip())
                    current_part = ""
            current_part += line + "\n"
    
    if current_part:
        parts.append(current_part.strip())
    
    return parts


async def safe_edit_text(message: types.Message, text: str, parse_mode: str = "HTML") -> bool:
    """Безопасно редактирует текст сообщения с обработкой ошибок."""
    try:
        await message.edit_text(text, parse_mode=parse_mode)
        return True
    except TelegramBadRequest as e:
        if "message to edit not found" in str(e).lower() or "message is not modified" in str(e).lower():
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            return False
        raise
    except Exception as e:
        logger.error(f"Ошибка при редактировании сообщения: {e}")
        return False


async def safe_delete(message: types.Message) -> bool:
    """Безопасно удаляет сообщение с обработкой ошибок."""
    try:
        await message.delete()
        return True
    except TelegramBadRequest as e:
        if "message to delete not found" in str(e).lower():
            logger.warning(f"Не удалось удалить сообщение: {e}")
            return False
        raise
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения: {e}")
        return False


async def safe_answer(message: types.Message, text: str, parse_mode: str = "HTML") -> types.Message | None:
    """Безопасно отправляет ответное сообщение с обработкой ошибок.
    
    Автоматически разбивает длинные сообщения на части, если они превышают лимит Telegram.
    """
    try:
        return await message.answer(text, parse_mode=parse_mode)
    except TelegramBadRequest as e:
        error_str = str(e).lower()
        if "file is too big" in error_str or "message is too long" in error_str:
            logger.warning(f"Сообщение слишком длинное, разбиваю на части: {e}")
            # Разбиваем сообщение на части
            parts = split_long_message(text, MAX_MESSAGE_LENGTH)
            last_msg = None
            for i, part in enumerate(parts):
                try:
                    if i == 0:
                        # Первая часть отправляется как новое сообщение
                        last_msg = await message.answer(part, parse_mode=parse_mode)
                    else:
                        # Остальные части отправляются как ответы на предыдущее сообщение
                        if last_msg:
                            last_msg = await last_msg.answer(part, parse_mode=parse_mode)
                        else:
                            last_msg = await message.answer(part, parse_mode=parse_mode)
                except TelegramBadRequest as part_error:
                    error_part_str = str(part_error).lower()
                    if "message is too long" in error_part_str:
                        # Если часть все еще слишком длинная, разбиваем её еще больше
                        logger.warning(f"Часть {i+1} все еще слишком длинная, разбиваю дальше: {part_error}")
                        smaller_parts = split_long_message(part, MAX_MESSAGE_LENGTH // 2)
                        for j, smaller_part in enumerate(smaller_parts):
                            try:
                                if i == 0 and j == 0:
                                    last_msg = await message.answer(smaller_part, parse_mode=parse_mode)
                                elif last_msg:
                                    last_msg = await last_msg.answer(smaller_part, parse_mode=parse_mode)
                                else:
                                    last_msg = await message.answer(smaller_part, parse_mode=parse_mode)
                            except Exception as smaller_error:
                                logger.error(f"Ошибка при отправке подчасти {j+1} части {i+1}: {smaller_error}")
                    else:
                        logger.error(f"Ошибка при отправке части сообщения {i+1}/{len(parts)}: {part_error}")
                except Exception as part_error:
                    logger.error(f"Ошибка при отправке части сообщения {i+1}/{len(parts)}: {part_error}")
            return last_msg
        raise
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        return None


def get_file_extension(file_type: FileType, original_filename: str | None = None) -> str:
    """Определяет расширение файла на основе типа."""
    if file_type == FileType.VOICE:
        return AudioFormat.OGG.value
    elif file_type == FileType.AUDIO:
        if original_filename:
            ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
            # Проверяем, что расширение поддерживается
            if ext in [fmt.value for fmt in AudioFormat]:
                return ext
        return AudioFormat.MP3.value
    elif file_type == FileType.VIDEO:
        if original_filename:
            ext = os.path.splitext(original_filename)[1].lower().lstrip(".")
            # Проверяем, что расширение поддерживается (включая mkv)
            if ext in [fmt.value for fmt in VideoFormat]:
                return ext
        return VideoFormat.MP4.value
    elif file_type == FileType.VIDEO_NOTE:
        return VideoFormat.MP4.value
    return AudioFormat.MP3.value


@router.message(Command(commands=["transcribe", "транскрибация"]))
async def transcribe_command_handler(message: types.Message) -> None:
    """Обработчик команды /transcribe - ожидает аудио или голосовое сообщение."""
    await message.answer(
        "🎙️ <b>Транскрибация аудио и видео</b>\n\n"
        "📤 <b>Отправьте файл одним из способов:</b>\n"
        "• 🎤 Голосовое сообщение\n"
        "• 🎵 Аудио файл\n"
        "• 🎬 Видео файл\n"
        "• 📎 Документ (аудио/видео)\n\n"
        "🎵 <b>Поддерживаемые аудио форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in AudioFormat])}</code>\n\n"
        "🎬 <b>Поддерживаемые видео форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in VideoFormat])}</code>\n\n"
        "💡 Файлы можно отправлять как медиа или документы.",
        parse_mode="HTML",
    )


def is_video_format(filename: str | None) -> bool:
    """Проверяет, является ли файл видео форматом."""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in [fmt.value for fmt in VideoFormat]


def is_audio_format(filename: str | None) -> bool:
    """Проверяет, является ли файл аудио форматом."""
    if not filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in [fmt.value for fmt in AudioFormat]


@router.message(F.voice | F.audio | F.video | F.video_note | F.document)
async def transcribe_handler(message: types.Message) -> None:
    """Обработчик транскрибации голосовых сообщений, аудио и видео файлов."""
    status_msg = await safe_answer(message, "⏳ <b>Начинаю транскрибацию...</b>", parse_mode="HTML")
    
    if not status_msg:
        logger.error("Не удалось отправить начальное статусное сообщение")
        return

    if not message.bot:
        await safe_edit_text(status_msg, "❌ <b>Ошибка:</b> бот не инициализирован.", parse_mode="HTML")
        return

    # Определяем файл для скачивания
    file_id: str | None = None
    file_name: str | None = None
    file_type: FileType | None = None

    if message.voice:
        file_id = message.voice.file_id
        file_type = FileType.VOICE
        file_name = f"voice_{file_id}.{get_file_extension(FileType.VOICE)}"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = FileType.AUDIO
        original_name = message.audio.file_name
        ext = get_file_extension(FileType.AUDIO, original_name)
        file_name = original_name or f"audio_{file_id}.{ext}"
    elif message.video:
        file_id = message.video.file_id
        file_type = FileType.VIDEO
        original_name = message.video.file_name
        ext = get_file_extension(FileType.VIDEO, original_name)
        file_name = original_name or f"video_{file_id}.{ext}"
    elif message.video_note:
        file_id = message.video_note.file_id
        file_type = FileType.VIDEO_NOTE
        file_name = f"video_note_{file_id}.{get_file_extension(FileType.VIDEO_NOTE)}"
    elif message.document:
        # Обрабатываем документы, которые могут быть видео или аудио файлами
        original_name = message.document.file_name
        if is_video_format(original_name):
            file_id = message.document.file_id
            file_type = FileType.VIDEO
            ext = get_file_extension(FileType.VIDEO, original_name)
            file_name = original_name or f"video_{file_id}.{ext}"
        elif is_audio_format(original_name):
            file_id = message.document.file_id
            file_type = FileType.AUDIO
            ext = get_file_extension(FileType.AUDIO, original_name)
            file_name = original_name or f"audio_{file_id}.{ext}"
        else:
            await safe_edit_text(
                status_msg,
                "❌ <b>Неподдерживаемый формат файла</b>\n\n"
                f"🎵 <b>Аудио:</b> <code>{', '.join([fmt.value.upper() for fmt in AudioFormat])}</code>\n"
                f"🎬 <b>Видео:</b> <code>{', '.join([fmt.value.upper() for fmt in VideoFormat])}</code>",
                parse_mode="HTML",
            )
            return
    else:
        await safe_edit_text(status_msg, "❌ <b>Не удалось определить тип файла.</b>", parse_mode="HTML")
        return

    if not file_id or not file_name:
        await safe_edit_text(status_msg, "❌ <b>Не удалось определить файл для транскрибации.</b>", parse_mode="HTML")
        return

    try:
        # Скачиваем файл
        file_info = await message.bot.get_file(file_id)

        if not file_info.file_path:
            await safe_edit_text(status_msg, "❌ <b>Не удалось получить путь к файлу.</b>", parse_mode="HTML")
            return

        # Создаем временную директорию для работы
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, file_name)

            # Скачиваем файл
            await safe_edit_text(status_msg, "📥 <b>Скачиваю файл...</b>", parse_mode="HTML")
            await message.bot.download_file(file_info.file_path, temp_file_path)
            logger.info(f"Файл скачан: {temp_file_path}, тип: {file_type.value if file_type else 'unknown'}")

            # Запускаем транскрибацию в отдельном потоке
            await safe_edit_text(
                status_msg,
                "🔄 <b>Обрабатываю аудио...</b>\n"
                "⏱ Это может занять некоторое время",
                parse_mode="HTML",
            )

            transcribed_text = await transcribe_audio(
                file_path=temp_file_path,
                model="medium",
                language="Russian",
                device=settings.transcribe.DEVICE,
            )

            if transcribed_text:
                await safe_delete(status_msg)
                await safe_answer(
                    message,
                    f"✅ <b>Транскрибация завершена</b>\n\n"
                    f"📝 <b>Текст:</b>\n{transcribed_text}",
                    parse_mode="HTML",
                )
                logger.info(f"Транскрибация завершена для файла {file_name}")
            else:
                await safe_edit_text(status_msg, "⚠️ <b>Не удалось распознать текст в аудио.</b>", parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await safe_edit_text(
            status_msg,
            f"❌ <b>Произошла ошибка при транскрибации</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
        )
