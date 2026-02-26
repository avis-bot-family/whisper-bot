import asyncio
import html
import os
import re
import tempfile
from datetime import datetime

from aiogram import F, Router, types
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter, Command, StateFilter
from aiogram.fsm.context import FSMContext
from loguru import logger

from bot.enums.file_formats import AudioFormat, FileType, VideoFormat
from bot.settings import Settings
from bot.states import TranscribeDiarizeState
from bot.schemas.summary import SummaryRequest
from bot.utils.diarize import transcribe_with_diarization
from bot.utils.download import download_file_with_progress, FileDownloadError
from bot.utils.google_drive import download_from_google_drive, extract_google_drive_file_id
from bot.utils.summary_generator import SummaryGenerator, format_summary_for_display
from bot.utils.transcribe import transcribe_audio

settings = Settings()

router = Router(name="transcribe")

# Максимальная длина сообщения в Telegram (с запасом для HTML-тегов)
# Telegram лимит: 4096 символов, но с HTML-тегами лучше использовать меньше
MAX_MESSAGE_LENGTH = 3500

# Максимальный размер файла для транскрибации (в байтах)
# 500 MB - разумный лимит для обработки
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

# Максимальная длина части транскрипции с учётом HTML-обёртки <pre>...</pre>
PRE_MAX = 3300


@router.message(Command(commands=["transcribe", "транскрибация"]))
async def transcribe_command_handler(message: types.Message, state: FSMContext) -> None:
    """Обработчик команды /transcribe - ожидает аудио или голосовое сообщение."""
    await state.clear()
    diarize_hint = ""
    if settings.transcribe.DIARIZE_BY_DEFAULT and settings.transcribe.HF_TOKEN:
        diarize_hint = "\n👥 <b>По умолчанию включена диаризация спикеров</b>\n\n"
    await message.answer(
        "🎙️ <b>Транскрибация аудио и видео</b>\n\n"
        f"{diarize_hint}"
        "📤 <b>Отправьте файл одним из способов:</b>\n"
        "• 🎤 Голосовое сообщение\n"
        "• 🎵 Аудио файл\n"
        "• 🎬 Видео файл\n"
        "• 📎 Документ (аудио/видео)\n\n"
        "🎵 <b>Поддерживаемые аудио форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in AudioFormat])}</code>\n\n"
        "🎬 <b>Поддерживаемые видео форматы:</b>\n"
        f"<code>{', '.join([fmt.value.upper() for fmt in VideoFormat])}</code>\n\n"
        "💡 Файлы можно отправлять как медиа или документы.\n\n"
        "🔗 Также можно отправить <b>ссылку на аудио/видео в Google Drive</b> (файл должен быть доступен по ссылке).",
        parse_mode="HTML",
    )


@router.message(Command(commands=["transcribe_diarize", "диаризация"]))
async def transcribe_diarize_command_handler(message: types.Message, state: FSMContext) -> None:
    """Обработчик команды /transcribe_diarize - транскрибация с определением спикеров."""
    hf_token = settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN")
    if not hf_token:
        await message.answer(
            "❌ <b>Диаризация недоступна</b>\n\n"
            "Для работы нужен HuggingFace токен. Добавьте в .env:\n"
            "<code>transcribe_HF_TOKEN=ваш_токен</code>\n\n"
            "Примите условия: "
            "<a href='https://huggingface.co/pyannote/speaker-diarization-community-1'>pyannote/speaker-diarization-community-1</a>",
            parse_mode="HTML",
        )
        return
    await state.set_state(TranscribeDiarizeState.waiting_for_file)
    await message.answer(
        "👥 <b>Транскрибация со спикерами</b>\n\n"
        "📤 <b>Отправьте аудио или видео файл</b> — бот определит, кто когда говорил.\n\n"
        "🎵 Подходят: голосовые, аудио, видео, документы.\n\n"
        "⏱ Обработка займёт больше времени, чем обычная транскрибация.",
        parse_mode="HTML",
    )


def format_time(seconds: float) -> str:
    """Форматирует время в секундах в формат MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_transcription_with_timestamps(segments: list[dict]) -> str:
    """Форматирует транскрибацию с таймкодами из сегментов Whisper."""
    if not segments:
        return ""

    formatted_parts = []
    for segment in segments:
        start_time = segment.get("start", 0)
        end_time = segment.get("end", 0)
        text = segment.get("text", "").strip()

        if text:
            time_str = f"[{format_time(start_time)} → {format_time(end_time)}]"
            formatted_parts.append(f"{time_str} {text}")

    return "\n".join(formatted_parts)


def format_transcription_diarized(segments: list[dict]) -> str:
    """Форматирует транскрибацию с таймкодами и спикерами."""
    if not segments:
        return ""

    formatted_parts = []
    for segment in segments:
        start_time = segment.get("start", 0)
        end_time = segment.get("end", 0)
        speaker = segment.get("speaker", "SPEAKER_00")
        text = segment.get("text", "").strip()

        if text:
            time_str = f"[{format_time(start_time)} → {format_time(end_time)}]"
            formatted_parts.append(f"{time_str} {speaker}: {text}")

    return "\n".join(formatted_parts)


def _extract_speakers_from_segments(segments: list[dict]) -> str:
    """Извлекает уникальных спикеров из сегментов для SummaryRequest."""
    speakers = set()
    for seg in segments:
        sp = seg.get("speaker")
        if sp:
            speakers.add(sp)
    if speakers:
        return "\n".join(f"- {s}" for s in sorted(speakers))
    return "(не определены)"


async def _try_generate_and_send_summary(
    message: types.Message,
    segments: list[dict],
    transcription_text: str,
    use_diarize: bool,
) -> None:
    """Генерирует и отправляет AI summary по аналогии с generate_summary_local.py."""
    base_url = settings.summary.BASE_URL or os.environ.get("SUMMARY_BASE_URL", "")
    if not base_url or not settings.summary.ENABLE_AFTER_TRANSCRIBE:
        return

    status_msg: types.Message | None = None
    try:
        participants = (
            _extract_speakers_from_segments(segments)
            if use_diarize and segments
            else "(не определены)"
        )
        meeting_date = datetime.now().strftime("%Y-%m-%d")

        request = SummaryRequest(
            meeting_date=meeting_date,
            participants_formatted=participants,
            context_hints="(не указан)",
            transcription_text=transcription_text,
        )

        generator = SummaryGenerator(
            base_url=base_url,
            model=settings.summary.MODEL,
            max_retries=settings.summary.MAX_RETRIES,
            request_timeout=settings.summary.REQUEST_TIMEOUT,
        )

        status_msg = await safe_answer(
            message,
            "⏳ <b>Генерирую AI summary...</b>",
            parse_mode="HTML",
        )
        if not status_msg:
            return

        summary_result = await generator.generate(request)
        await safe_delete(status_msg)

        formatted = format_summary_for_display(summary_result)
        await safe_answer(message, formatted)
        logger.info("Summary сгенерирован и отправлен")
    except Exception as e:
        logger.warning(f"Не удалось сгенерировать summary: {e}")
        if status_msg:
            await safe_edit_text(
                status_msg,
                f"⚠️ <b>Summary недоступен</b>\n\n<code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
            )
        # Не прерываем — транскрибация уже отправлена


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


def _parse_retry_after(error: Exception) -> float | None:
    """Извлекает время ожидания (в секундах) из ошибки Flood / retry after."""
    m = re.search(r"(?:retry in |retry after )(\d+)", str(error), re.I)
    return float(m.group(1)) + 0.5 if m else None


async def safe_edit_text(message: types.Message, text: str, parse_mode: str = "HTML") -> bool:
    """Безопасно редактирует текст сообщения с обработкой ошибок.
    При Flood control / Too Many Requests выполняет одну повторную попытку после задержки.
    """
    try:
        await message.edit_text(text, parse_mode=parse_mode)
        return True
    except TelegramBadRequest as e:
        err = str(e).lower()
        if "message to edit not found" in err or "message is not modified" in err:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            return False
        if "flood" in err or "retry after" in err or "too many requests" in err:
            sec = _parse_retry_after(e)
            if sec and sec > 0:
                logger.warning(f"Flood control, жду {sec:.1f} с перед повтором: {e}")
                await asyncio.sleep(sec)
                try:
                    await message.edit_text(text, parse_mode=parse_mode)
                    return True
                except Exception as retry_e:
                    logger.error(f"Повтор после flood не удался: {retry_e}")
                    return False
        raise
    except Exception as e:
        err = str(e).lower()
        if "flood" in err or "retry after" in err or "too many requests" in err:
            sec = _parse_retry_after(e)
            if sec and sec > 0:
                logger.warning(f"Flood control (через Exception), жду {sec:.1f} с: {e}")
                await asyncio.sleep(sec)
                try:
                    await message.edit_text(text, parse_mode=parse_mode)
                    return True
                except Exception as retry_e:
                    logger.error(f"Повтор после flood не удался: {retry_e}")
                    return False
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
            # Разбиваем по символам/строкам — разметка HTML при этом может порваться,
            # поэтому части уходим без parse_mode, чтобы не получить can't parse entities.
            parts = split_long_message(text, MAX_MESSAGE_LENGTH)
            part_parse_mode: str | None = None
            last_msg = None
            for i, part in enumerate(parts):
                try:
                    if i == 0:
                        last_msg = await message.answer(part, parse_mode=part_parse_mode)
                    else:
                        if last_msg:
                            last_msg = await last_msg.answer(part, parse_mode=part_parse_mode)
                        else:
                            last_msg = await message.answer(part, parse_mode=part_parse_mode)
                except TelegramBadRequest as part_error:
                    error_part_str = str(part_error).lower()
                    if "message is too long" in error_part_str:
                        logger.warning(f"Часть {i + 1} все еще слишком длинная, разбиваю дальше: {part_error}")
                        smaller_parts = split_long_message(part, MAX_MESSAGE_LENGTH // 2)
                        for j, smaller_part in enumerate(smaller_parts):
                            try:
                                if i == 0 and j == 0:
                                    last_msg = await message.answer(smaller_part, parse_mode=part_parse_mode)
                                elif last_msg:
                                    last_msg = await last_msg.answer(smaller_part, parse_mode=part_parse_mode)
                                else:
                                    last_msg = await message.answer(smaller_part, parse_mode=part_parse_mode)
                            except Exception as smaller_error:
                                logger.error(f"Ошибка при отправке подчасти {j + 1} части {i + 1}: {smaller_error}")
                    else:
                        logger.error(f"Ошибка при отправке части сообщения {i + 1}/{len(parts)}: {part_error}")
                except Exception as part_error:
                    logger.error(f"Ошибка при отправке части сообщения {i + 1}/{len(parts)}: {part_error}")
            return last_msg
        raise
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
        return None


class GoogleDriveLinkFilter(BaseFilter):
    """Фильтр: сообщение содержит ссылку на Google Drive."""

    async def __call__(self, message: types.Message) -> bool:
        if not message.text:
            return False
        return extract_google_drive_file_id((message.text or "").strip()) is not None


async def send_transcription_result(
    message: types.Message,
    formatted_text: str,
    pre_max: int = PRE_MAX,
) -> None:
    """Отправляет транскрипцию: сообщением если помещается, иначе .txt файлом."""
    if len(formatted_text) <= pre_max:
        safe_part = html.escape(formatted_text)
        text_out = "✅ <b>Транскрибация завершена</b>\n\n" "📝 <b>Текст с таймкодами:</b>\n\n" f"<pre>{safe_part}</pre>"
        await safe_answer(message, text_out, parse_mode="HTML")
    else:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(formatted_text)
            temp_path = f.name
        try:
            await message.answer_document(
                FSInputFile(temp_path, filename="transcription.txt"),
                caption="✅ Транскрибация завершена\n📝 Текст с таймкодами",
            )
        finally:
            try:
                os.unlink(temp_path)
            except OSError as e:
                logger.warning(f"Не удалось удалить временный файл {temp_path}: {e}")


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


@router.message(GoogleDriveLinkFilter())
async def transcribe_google_drive_link_handler(message: types.Message) -> None:
    """Обработчик транскрибации по ссылке на файл в Google Drive."""
    text = (message.text or "").strip()
    gdrive_file_id = extract_google_drive_file_id(text)
    if not gdrive_file_id:
        return

    status_msg: types.Message | None = None
    try:
        status_msg = await safe_answer(
            message,
            "⏳ <b>Начинаю транскрибацию по ссылке Google Drive...</b>",
            parse_mode="HTML",
        )
        if not status_msg:
            logger.error("Не удалось отправить начальное статусное сообщение")
            return
        with tempfile.TemporaryDirectory() as temp_dir:
            # Расширение по умолчанию для аудио; Whisper определит формат по содержимому
            temp_file_path = os.path.join(temp_dir, f"gdrive_{gdrive_file_id}.mp3")

            await safe_edit_text(status_msg, "📥 <b>Скачиваю файл с Google Drive...</b>", parse_mode="HTML")
            try:
                await download_from_google_drive(
                    file_id=gdrive_file_id,
                    destination_path=temp_file_path,
                    status_message=status_msg,
                    update_status_func=safe_edit_text,
                )
            except OSError as e:
                logger.error(f"Ошибка скачивания с Google Drive: {e}")
                await safe_edit_text(
                    status_msg,
                    f"❌ <b>Не удалось скачать файл с Google Drive</b>\n\n"
                    f"<code>{html.escape(str(e))}</code>\n\n"
                    "💡 Убедитесь, что ссылка публичная (доступ «все, у кого есть ссылка»).",
                    parse_mode="HTML",
                )
                return

            if not os.path.exists(temp_file_path) or os.path.getsize(temp_file_path) == 0:
                await safe_edit_text(
                    status_msg,
                    "⚠️ <b>Файл пустой или не удалось скачать.</b>",
                    parse_mode="HTML",
                )
                return

            file_size = os.path.getsize(temp_file_path)
            if file_size > MAX_FILE_SIZE:
                await safe_edit_text(
                    status_msg,
                    f"❌ <b>Файл слишком большой</b>\n\n"
                    f"📏 Максимальный размер: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB",
                    parse_mode="HTML",
                )
                return

            use_diarize = (
                settings.transcribe.DIARIZE_BY_DEFAULT
                and (settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN"))
            )
            status_text = (
                "🔄 <b>Транскрибация и диаризация...</b>\n⏱ Это займёт больше времени"
                if use_diarize
                else "🔄 <b>Обрабатываю аудио...</b>\n⏱ Это может занять некоторое время"
            )
            await safe_edit_text(status_msg, status_text, parse_mode="HTML")

            if use_diarize:
                hf_token = settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN")
                transcription_result = await transcribe_with_diarization(
                    file_path=temp_file_path,
                    model=settings.transcribe.MODEL,
                    language=settings.transcribe.LANGUAGE,
                    device=settings.transcribe.DEVICE,
                    hf_token=hf_token,
                    min_speakers=settings.transcribe.DIARIZE_MIN_SPEAKERS,
                    max_speakers=settings.transcribe.DIARIZE_MAX_SPEAKERS,
                )
                format_fn = format_transcription_diarized
            else:
                transcription_result = await transcribe_audio(
                    file_path=temp_file_path,
                    model=settings.transcribe.MODEL,
                    language=settings.transcribe.LANGUAGE,
                    device=settings.transcribe.DEVICE,
                )
                format_fn = format_transcription_with_timestamps

            if transcription_result and transcription_result.get("text"):
                await safe_delete(status_msg)
                segments = transcription_result.get("segments", [])
                formatted_text = format_fn(segments) if segments else transcription_result["text"]
                await send_transcription_result(message, formatted_text)
                await _try_generate_and_send_summary(
                    message, segments, formatted_text, use_diarize
                )
                logger.info("Транскрибация по ссылке Google Drive завершена")
            else:
                await safe_edit_text(status_msg, "⚠️ <b>Не удалось распознать текст в аудио.</b>", parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ошибка при транскрибации по ссылке Google Drive: {e}")
        if status_msg is not None:
            await safe_edit_text(
                status_msg,
                f"❌ <b>Произошла ошибка</b>\n\n<code>{html.escape(str(e))}</code>",
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


@router.message(
    StateFilter(TranscribeDiarizeState.waiting_for_file),
    F.voice | F.audio | F.video | F.video_note | F.document,
)
async def transcribe_diarize_handler(message: types.Message, state: FSMContext) -> None:
    """Обработчик транскрибации с диаризацией (когда пользователь в режиме /transcribe_diarize)."""
    await state.clear()
    status_msg = await safe_answer(
        message,
        "⏳ <b>Начинаю транскрибацию со спикерами...</b>",
        parse_mode="HTML",
    )
    if not status_msg or not message.bot:
        if status_msg:
            await safe_edit_text(status_msg, "❌ <b>Ошибка:</b> бот не инициализирован.", parse_mode="HTML")
        return

    file_id, file_name, file_type, file_size = await _extract_file_info(message, status_msg)
    if not file_id or not file_name:
        return

    try:
        file_info = await _get_and_validate_file(message, file_id, file_size, status_msg)
        if not file_info:
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, file_name)
            await safe_edit_text(status_msg, "📥 <b>Скачиваю файл...</b>", parse_mode="HTML")
            if not await _download_file(message, file_info, temp_file_path, status_msg):
                return

            await safe_edit_text(
                status_msg,
                "🔄 <b>Транскрибация и диаризация...</b>\n⏱ Это займёт больше времени",
                parse_mode="HTML",
            )

            hf_token = settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN")
            result = await transcribe_with_diarization(
                file_path=temp_file_path,
                model=settings.transcribe.MODEL,
                language=settings.transcribe.LANGUAGE,
                device=settings.transcribe.DEVICE,
                hf_token=hf_token,
                min_speakers=settings.transcribe.DIARIZE_MIN_SPEAKERS,
                max_speakers=settings.transcribe.DIARIZE_MAX_SPEAKERS,
            )

            if result and result.get("text"):
                await safe_delete(status_msg)
                segments = result.get("segments", [])
                formatted = format_transcription_diarized(segments) if segments else result["text"]
                await send_transcription_result(message, formatted)
                await _try_generate_and_send_summary(
                    message, segments, formatted, use_diarize=True
                )
                logger.info(f"Транскрибация с диаризацией завершена: {file_name}")
            else:
                await safe_edit_text(status_msg, "⚠️ <b>Не удалось распознать текст в аудио.</b>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка при диаризации: {e}")
        if status_msg:
            await safe_edit_text(
                status_msg,
                f"❌ <b>Ошибка при диаризации</b>\n\n<code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
            )


async def _extract_file_info(message: types.Message, status_msg: types.Message | None) -> tuple:
    """Извлекает file_id, file_name, file_type, file_size из сообщения."""
    file_id = file_name = file_type = file_size = None
    if message.voice:
        file_id = message.voice.file_id
        file_type = FileType.VOICE
        file_name = f"voice_{file_id}.{get_file_extension(FileType.VOICE)}"
        file_size = getattr(message.voice, "file_size", None)
    elif message.audio:
        file_id = message.audio.file_id
        file_type = FileType.AUDIO
        ext = get_file_extension(FileType.AUDIO, message.audio.file_name)
        file_name = message.audio.file_name or f"audio_{file_id}.{ext}"
        file_size = getattr(message.audio, "file_size", None)
    elif message.video:
        file_id = message.video.file_id
        file_type = FileType.VIDEO
        ext = get_file_extension(FileType.VIDEO, message.video.file_name)
        file_name = message.video.file_name or f"video_{file_id}.{ext}"
        file_size = getattr(message.video, "file_size", None)
    elif message.video_note:
        file_id = message.video_note.file_id
        file_type = FileType.VIDEO_NOTE
        file_name = f"video_note_{file_id}.{get_file_extension(FileType.VIDEO_NOTE)}"
        file_size = getattr(message.video_note, "file_size", None)
    elif message.document:
        orig = message.document.file_name
        file_size = getattr(message.document, "file_size", None)
        if is_video_format(orig):
            file_id = message.document.file_id
            file_type = FileType.VIDEO
            ext = get_file_extension(FileType.VIDEO, orig)
            file_name = orig or f"video_{file_id}.{ext}"
        elif is_audio_format(orig):
            file_id = message.document.file_id
            file_type = FileType.AUDIO
            ext = get_file_extension(FileType.AUDIO, orig)
            file_name = orig or f"audio_{file_id}.{ext}"
        elif status_msg:
            await safe_edit_text(
                status_msg,
                "❌ <b>Неподдерживаемый формат</b>\n\n"
                f"Аудио: {', '.join([f.value.upper() for f in AudioFormat])}\n"
                f"Видео: {', '.join([f.value.upper() for f in VideoFormat])}",
                parse_mode="HTML",
            )
    return (file_id, file_name, file_type, file_size)


async def _get_and_validate_file(
    message: types.Message, file_id: str, file_size: int | None, status_msg: types.Message | None
) -> types.File | None:
    """Получает file_info и проверяет размер."""
    try:
        file_info = await message.bot.get_file(file_id)  # type: ignore[union-attr]
    except TelegramBadRequest as e:
        if "file is too big" in str(e).lower() and status_msg:
            await safe_edit_text(
                status_msg,
                "❌ <b>Файл >20 MB</b>\n\nЛимит getFile: 20 MB.",
                parse_mode="HTML",
            )
        else:
            raise
        return None
    if not file_info.file_path:
        if status_msg:
            await safe_edit_text(status_msg, "❌ <b>Не удалось получить путь к файлу.</b>", parse_mode="HTML")
        return None
    fs = getattr(file_info, "file_size", None) or file_size
    if fs and fs > MAX_FILE_SIZE and status_msg:
        await safe_edit_text(
            status_msg,
            f"❌ <b>Файл слишком большой</b>\n\nМакс: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB",
            parse_mode="HTML",
        )
        return None
    return file_info


async def _download_file(
    message: types.Message,
    file_info: types.File,
    dest: str,
    status_msg: types.Message | None,
) -> bool:
    """Скачивает файл. Возвращает False при ошибке."""
    try:
        await download_file_with_progress(
            bot=message.bot,
            file_info=file_info,
            destination_path=dest,
            status_message=status_msg,
            update_status_func=safe_edit_text,
        )
        if os.path.getsize(dest) == 0 and status_msg:
            await safe_edit_text(status_msg, "⚠️ <b>Файл пустой.</b>", parse_mode="HTML")
            return False
        return True
    except (TelegramBadRequest, FileDownloadError) as e:
        if "file is too big" in str(e).lower() and status_msg:
            await safe_edit_text(
                status_msg,
                f"❌ <b>Файл слишком большой</b>\n\nМакс: {MAX_FILE_SIZE / (1024 * 1024):.0f} MB",
                parse_mode="HTML",
            )
        else:
            raise
        return False


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
    file_size: int | None = None

    if message.voice:
        file_id = message.voice.file_id
        file_type = FileType.VOICE
        file_name = f"voice_{file_id}.{get_file_extension(FileType.VOICE)}"
        file_size = getattr(message.voice, "file_size", None)
    elif message.audio:
        file_id = message.audio.file_id
        file_type = FileType.AUDIO
        original_name = message.audio.file_name
        ext = get_file_extension(FileType.AUDIO, original_name)
        file_name = original_name or f"audio_{file_id}.{ext}"
        file_size = getattr(message.audio, "file_size", None)
    elif message.video:
        file_id = message.video.file_id
        file_type = FileType.VIDEO
        original_name = message.video.file_name
        ext = get_file_extension(FileType.VIDEO, original_name)
        file_name = original_name or f"video_{file_id}.{ext}"
        file_size = getattr(message.video, "file_size", None)
    elif message.video_note:
        file_id = message.video_note.file_id
        file_type = FileType.VIDEO_NOTE
        file_name = f"video_note_{file_id}.{get_file_extension(FileType.VIDEO_NOTE)}"
        file_size = getattr(message.video_note, "file_size", None)
    elif message.document:
        # Обрабатываем документы, которые могут быть видео или аудио файлами
        original_name = message.document.file_name
        file_size = getattr(message.document, "file_size", None)
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
        # Получаем информацию о файле (getFile). По доке: File потом качаем по
        # https://api.telegram.org/file/bot<token>/<file_path>. getFile не работает для >20 MB.
        try:
            file_info = await message.bot.get_file(file_id)
        except TelegramBadRequest as e:
            if "file is too big" in str(e).lower():
                size_mb = (file_size or 0) / (1024 * 1024)
                await safe_edit_text(
                    status_msg,
                    "❌ <b>Файл слишком большой для getFile (Bot API)</b>\n\n"
                    f"📊 <b>Размер:</b> {size_mb:.1f} MB\n"
                    "📏 <b>Лимит getFile:</b> 20 MB\n\n"
                    "💡 Telegram Bot API не отдаёт <code>file_path</code> для файлов >20 MB. "
                    "Отправьте файл до 20 MB.",
                    parse_mode="HTML",
                )
                return
            raise

        if not file_info.file_path:
            await safe_edit_text(status_msg, "❌ <b>Не удалось получить путь к файлу.</b>", parse_mode="HTML")
            return

        # Проверяем размер файла (из file_info или из сообщения)
        file_size = getattr(file_info, "file_size", None) or file_size
        if file_size and file_size > MAX_FILE_SIZE:
            file_size_mb = file_size / (1024 * 1024)
            max_size_mb = MAX_FILE_SIZE / (1024 * 1024)
            await safe_edit_text(
                status_msg,
                f"❌ <b>Файл слишком большой</b>\n\n"
                f"📊 <b>Размер файла:</b> {file_size_mb:.1f} MB\n"
                f"📏 <b>Максимальный размер:</b> {max_size_mb:.0f} MB\n\n"
                f"💡 Попробуйте отправить файл меньшего размера или разделите его на части.",
                parse_mode="HTML",
            )
            logger.warning(f"Файл слишком большой: {file_size_mb:.1f} MB (максимум: {max_size_mb:.0f} MB)")
            return

        # Создаем временную директорию для работы
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_file_path = os.path.join(temp_dir, file_name)

            # Скачиваем файл с использованием оптимизированного модуля
            await safe_edit_text(status_msg, "📥 <b>Скачиваю файл...</b>", parse_mode="HTML")
            try:
                await download_file_with_progress(
                    bot=message.bot,
                    file_info=file_info,
                    destination_path=temp_file_path,
                    status_message=status_msg,
                    update_status_func=safe_edit_text,
                )
                size_info = f", размер: {file_size / (1024 * 1024):.1f} MB" if file_size else ""
                logger.info(
                    f"Файл скачан: {temp_file_path}, тип: " f"{file_type.value if file_type else 'unknown'}{size_info}"
                )
            except (TelegramBadRequest, FileDownloadError) as download_error:
                error_str = str(download_error).lower()
                if "file is too big" in error_str:
                    await safe_edit_text(
                        status_msg,
                        f"❌ <b>Файл слишком большой для загрузки</b>\n\n"
                        f"📏 <b>Максимальный размер:</b> {MAX_FILE_SIZE / (1024 * 1024):.0f} MB\n\n"
                        f"💡 Telegram не позволяет загрузить файл такого размера.\n"
                        f"Попробуйте отправить файл меньшего размера.",
                        parse_mode="HTML",
                    )
                    logger.error(f"Ошибка при загрузке файла: {download_error}")
                    return
                raise

            # Проверка на пустой файл (0 байт)
            if os.path.getsize(temp_file_path) == 0:
                await safe_edit_text(
                    status_msg,
                    "⚠️ <b>Файл пустой или слишком короткий.</b>",
                    parse_mode="HTML",
                )
                return

            use_diarize = (
                settings.transcribe.DIARIZE_BY_DEFAULT
                and (settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN"))
            )
            status_text = (
                "🔄 <b>Транскрибация и диаризация...</b>\n⏱ Это займёт больше времени"
                if use_diarize
                else "🔄 <b>Обрабатываю аудио...</b>\n⏱ Это может занять некоторое время"
            )
            await safe_edit_text(status_msg, status_text, parse_mode="HTML")

            if use_diarize:
                hf_token = settings.transcribe.HF_TOKEN or os.environ.get("HF_TOKEN")
                transcription_result = await transcribe_with_diarization(
                    file_path=temp_file_path,
                    model=settings.transcribe.MODEL,
                    language=settings.transcribe.LANGUAGE,
                    device=settings.transcribe.DEVICE,
                    hf_token=hf_token,
                    min_speakers=settings.transcribe.DIARIZE_MIN_SPEAKERS,
                    max_speakers=settings.transcribe.DIARIZE_MAX_SPEAKERS,
                )
                format_fn = format_transcription_diarized
            else:
                transcription_result = await transcribe_audio(
                    file_path=temp_file_path,
                    model=settings.transcribe.MODEL,
                    language=settings.transcribe.LANGUAGE,
                    device=settings.transcribe.DEVICE,
                )
                format_fn = format_transcription_with_timestamps

            if transcription_result and transcription_result.get("text"):
                await safe_delete(status_msg)

                segments = transcription_result.get("segments", [])
                formatted_text = format_fn(segments) if segments else transcription_result["text"]
                await send_transcription_result(message, formatted_text)
                await _try_generate_and_send_summary(
                    message, segments, formatted_text, use_diarize
                )
                logger.info(f"Транскрибация завершена для файла {file_name}")
            else:
                await safe_edit_text(status_msg, "⚠️ <b>Не удалось распознать текст в аудио.</b>", parse_mode="HTML")

    except TelegramBadRequest as e:
        error_str = str(e).lower()
        if "file is too big" in error_str:
            logger.error(f"Файл слишком большой: {e}")
            await safe_edit_text(
                status_msg,
                f"❌ <b>Файл слишком большой</b>\n\n"
                f"📏 <b>Максимальный размер:</b> {MAX_FILE_SIZE / (1024 * 1024):.0f} MB\n\n"
                f"💡 Telegram не позволяет обработать файл такого размера.\n"
                f"Попробуйте отправить файл меньшего размера.",
                parse_mode="HTML",
            )
        else:
            logger.error(f"Ошибка Telegram API при обработке файла: {e}")
            await safe_edit_text(
                status_msg,
                f"❌ <b>Произошла ошибка при транскрибации</b>\n\n<code>{html.escape(str(e))}</code>",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        await safe_edit_text(
            status_msg,
            f"❌ <b>Произошла ошибка при транскрибации</b>\n\n<code>{html.escape(str(e))}</code>",
            parse_mode="HTML",
        )
