from aiogram import F, Router, types
from aiogram.filters import Command

from bot.enums.file_formats import AudioFormat, VideoFormat

router = Router(name="info")


@router.message(Command(commands=["info", "help", "about", "start"]))
async def info_handler(message: types.Message) -> None:
    """Information about bot."""
    message_text = (
        "🎙️ <b>Whisper Bot</b> - Транскрибация аудио и видео\n\n"
        "📝 <b>Возможности:</b>\n"
        "• Транскрибация голосовых сообщений\n"
        "• Распознавание речи в аудио файлах\n"
        "• Извлечение текста из видео\n\n"
        "🎵 <b>Поддерживаемые аудио форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in AudioFormat])}</code>\n\n"
        "🎬 <b>Поддерживаемые видео форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in VideoFormat])}</code>\n\n"
        "💡 <b>Как использовать:</b>\n"
        "1. Отправьте голосовое сообщение\n"
        "2. Или отправьте аудио/видео файл\n"
        "3. Бот автоматически распознает речь\n\n"
        "⚡ Используйте команду /transcribe для получения инструкций"
    )
    await message.answer(message_text, parse_mode="HTML")


@router.callback_query(F.data == "info")
async def info_callback(query: types.CallbackQuery) -> None:
    await info_handler(query.message)
    await query.answer()
