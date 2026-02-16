#!/usr/bin/env python3
"""
Скрипт для транскрибации с диаризацией спикеров (Whisper + pyannote.audio).

Использование:
    poetry run python src/scripts/transcribe_diarize_local.py [файл]
    poetry run python src/scripts/transcribe_diarize_local.py path/to/meeting.mp3 --diarize

Требования:
    - ffmpeg для конвертации аудио (simple-diarizer)
"""

import argparse
import os
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH для импорта bot
_script_dir = Path(__file__).resolve().parent
_src_dir = _script_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from bot.utils.diarize import transcribe_with_diarization_sync
from bot.utils.transcribe import _transcribe_audio_sync

# HF_TOKEN или transcribe_HF_TOKEN в .env

# Путь к файлу по умолчанию
DEFAULT_FILE = _script_dir.parent / "bot" / "audio" / "privet-druzya.mp3"


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Транскрибация с диаризацией спикеров (Whisper + pyannote.audio)",
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=DEFAULT_FILE,
        help=f"Путь к аудио/видео файлу (по умолчанию: {DEFAULT_FILE})",
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
        "--diarize",
        action="store_true",
        help="Включить диаризацию спикеров",
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Известное количество спикеров (опционально)",
    )
    parser.add_argument(
        "--min-speakers",
        type=int,
        default=None,
        help="Минимальное количество спикеров",
    )
    parser.add_argument(
        "--max-speakers",
        type=int,
        default=None,
        help="Максимальное количество спикеров",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Выводить только текст без таймкодов и спикеров",
    )
    args = parser.parse_args()

    file_path = args.file.resolve()
    if not file_path.exists():
        print(f"Ошибка: файл не найден: {file_path}")
        raise SystemExit(1)

    if args.diarize:
        hf_token = os.environ.get("HF_TOKEN") or os.environ.get("transcribe_HF_TOKEN")
        if not hf_token:
            print(
                "Ошибка: для диаризации нужен HF_TOKEN в .env\n"
                "Примите условия: https://huggingface.co/pyannote/speaker-diarization-community-1"
            )
            raise SystemExit(1)
        n_speakers = args.num_speakers
        if n_speakers is None and args.max_speakers is not None:
            n_speakers = args.max_speakers
        if n_speakers is None:
            n_speakers = 2
        result = transcribe_with_diarization_sync(
            str(file_path),
            model=args.model,
            language=args.language,
            device=args.device,
            hf_token=hf_token,
            num_speakers=n_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
        )
    else:
        result = _transcribe_audio_sync(
            str(file_path),
            model=args.model,
            language=args.language,
            device=args.device,
        )

    if args.plain:
        print(result["text"])
    elif result.get("segments"):
        segments = result["segments"]
        if args.diarize and any(s.get("speaker") for s in segments):
            print(format_diarized(segments))
        else:
            for seg in segments:
                start = seg.get("start", 0)
                end = seg.get("end", 0)
                text = seg.get("text", "").strip()
                if text:
                    print(f"[{format_time(start)} → {format_time(end)}] {text}")
    else:
        print(result["text"])


if __name__ == "__main__":
    main()
