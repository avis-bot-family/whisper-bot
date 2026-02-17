#!/usr/bin/env python3
"""
Скрипт для генерации AI Summary на основе транскрибации с диаризацией.

Использование:
    poetry run python src/scripts/generate_summary_local.py [файл]
    poetry run python src/scripts/generate_summary_local.py path/to/meeting.mp3

Требования:
    - Ollama: summary_BASE_URL=http://localhost:11434/v1 (по умолчанию)
    - HF_TOKEN для диаризации (если используется полный пайплайн)
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Добавляем src в PYTHONPATH для импорта bot
_script_dir = Path(__file__).resolve().parent
_src_dir = _script_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from bot.schemas.summary import SummaryRequest  # noqa: E402
from bot.settings import Settings  # noqa: E402
from bot.utils.diarize import transcribe_with_diarization_sync  # noqa: E402
from bot.utils.summary_generator import (  # noqa: E402
    SummaryGenerator,
    format_summary_for_display,
)


def format_time(seconds: float) -> str:
    """Форматирует время в секундах в формат MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_diarized(segments: list[dict]) -> str:
    """Форматирует сегменты с таймкодами и спикерами."""
    parts = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        speaker = seg.get("speaker", "SPEAKER_00")
        text = seg.get("text", "").strip()
        if text:
            parts.append(f"[{format_time(start)} → {format_time(end)}] {speaker}: {text}")
    return "\n".join(parts)


def extract_speakers(segments: list[dict]) -> list[str]:
    """Извлекает уникальных спикеров из сегментов."""
    speakers = set()
    for seg in segments:
        sp = seg.get("speaker")
        if sp:
            speakers.add(sp)
    return sorted(speakers)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генерация AI Summary на основе транскрибации с диаризацией",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=_script_dir.parent / "bot" / "audio" / "privet-druzya.mp3",
        help="Путь к аудио/видео файлу",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="Модель Whisper (tiny, base, small, medium, large)",
    )
    parser.add_argument(
        "--language",
        default="Russian",
        help="Язык аудио",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        choices=["cpu", "cuda"],
        help="Устройство для инференса",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=2,
        help="Количество спикеров для диаризации",
    )
    parser.add_argument(
        "--meeting-date",
        default=None,
        help="Дата встречи (по умолчанию — сегодня)",
    )
    parser.add_argument(
        "--context",
        default="",
        help="Дополнительный контекст встречи",
    )
    parser.add_argument(
        "--transcription",
        type=Path,
        default=None,
        help="Путь к файлу с готовой транскрибацией (пропустить Whisper+диаризацию)",
    )
    args = parser.parse_args()

    settings = Settings()
    base_url = settings.summary.BASE_URL or os.environ.get("SUMMARY_BASE_URL", "http://localhost:11434/v1")

    meeting_date = args.meeting_date or datetime.now().strftime("%Y-%m-%d")

    if args.transcription and args.transcription.exists():
        # Режим: только генерация summary из готовой транскрибации
        print(f"Читаю транскрибацию из {args.transcription}...")
        transcription_text = args.transcription.read_text(encoding="utf-8")
        participants_formatted = "(из файла)"
    else:
        # Режим: транскрибация + диаризация + summary
        file_path = args.file.resolve()
        if not file_path.exists():
            print(f"Ошибка: файл не найден: {file_path}")
            raise SystemExit(1)

        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("transcribe_HF_TOKEN")
        if not hf_token:
            print(
                "Ошибка: для диаризации нужен HF_TOKEN в .env\n"
                "Примите условия: https://huggingface.co/pyannote/speaker-diarization-community-1"
            )
            raise SystemExit(1)

        print(f"Транскрибация с диаризацией: {file_path}...")
        result = transcribe_with_diarization_sync(
            str(file_path),
            model=args.model,
            language=args.language,
            device=args.device,
            hf_token=hf_token,
            num_speakers=args.num_speakers,
        )
        segments = result.get("segments", [])
        transcription_text = format_diarized(segments)
        speakers = extract_speakers(segments)
        participants_formatted = "\n".join(f"- {s}" for s in speakers) if speakers else "(не определены)"

    request = SummaryRequest(
        meeting_date=meeting_date,
        participants_formatted=participants_formatted,
        context_hints=args.context or "(не указан)",
        transcription_text=transcription_text,
    )

    generator = SummaryGenerator(
        base_url=base_url,
        model=settings.summary.MODEL,
        max_retries=settings.summary.MAX_RETRIES,
        request_timeout=settings.summary.REQUEST_TIMEOUT,
    )

    print("\nГенерация summary...")
    summary_result = await generator.generate(request)
    print("\n" + format_summary_for_display(summary_result))


if __name__ == "__main__":
    asyncio.run(main())
