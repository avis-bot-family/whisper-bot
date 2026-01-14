import os
import tempfile

from aiogram import F, Router, types
from aiogram.filters import Command
from loguru import logger

from bot.enums.file_formats import AudioFormat, FileType, VideoFormat
from bot.settings import Settings
from bot.utils.transcribe import transcribe_audio

settings = Settings()

router = Router(name="transcribe")


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
    status_msg = await message.answer("⏳ <b>Начинаю транскрибацию...</b>", parse_mode="HTML")

    if not message.bot:
        await status_msg.edit_text("❌ <b>Ошибка:</b> бот не инициализирован.", parse_mode="HTML")
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
            await status_msg.edit_text(
                "❌ <b>Неподдерживаемый формат файла</b>\n\n"
                f"🎵 <b>Аудио:</b> <code>{', '.join([fmt.value.upper() for fmt in AudioFormat])}</code>\n"
                f"🎬 <b>Видео:</b> <code>{', '.join([fmt.value.upper() for fmt in VideoFormat])}</code>",
                parse_mode="HTML",
            )
            return
    else:
        await status_msg.edit_text("❌ <b>Не удалось определить тип файла.</b>", parse_mode="HTML")
        return

    if not file_id or not file_name:
        await status_msg.edit_text("❌ <b>Не удалось определить файл для транскрибации.</b>", parse_mode="HTML")
        return

    try:
        # Скачиваем файл
        file_info = await message.bot.get_file(file_id)

        if not file_info.file_path:
            await status_msg.edit_text("❌ <b>Не удалось получить путь к файлу.</b>", parse_mode="HTML")
            return

        # Создаем временную директорию для работы
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, file_name)

            # Скачиваем файл
            await status_msg.edit_text("📥 <b>Скачиваю файл...</b>", parse_mode="HTML")
            await message.bot.download_file(file_info.file_path, temp_file_path)
            logger.info(f"Файл скачан: {temp_file_path}, тип: {file_type.value if file_type else 'unknown'}")

            # Запускаем транскрибацию в отдельном потоке
            await status_msg.edit_text(
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
                await status_msg.delete()
                await message.answer(
                    f"✅ <b>Транскрибация завершена</b>\n\n"
                    f"📝 <b>Текст:</b>\n{transcribed_text}",
                    parse_mode="HTML",
                )
                logger.info(f"Транскрибация завершена для файла {file_name}")
            else:
                await status_msg.edit_text("⚠️ <b>Не удалось распознать текст в аудио.</b>", parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await status_msg.edit_text(
            f"❌ <b>Произошла ошибка при транскрибации</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
        )
