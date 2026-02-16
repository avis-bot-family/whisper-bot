#!/usr/bin/env python3
"""
Скрипт для транскрибации локальных аудио/видео файлов.

Использование:
    poetry run python src/scripts/transcribe_local.py [файл]
    poetry run python src/scripts/transcribe_local.py path/to/audio.mp3

Если файл не указан, используется src/bot/audio/privet-druzya.mp3 по умолчанию.
"""

import argparse
import sys
from pathlib import Path

# Добавляем src в PYTHONPATH для импорта bot
_script_dir = Path(__file__).resolve().parent
_src_dir = _script_dir.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from bot.utils.transcribe import _transcribe_audio_sync

# Путь к файлу по умолчанию (относительно расположения скрипта)
DEFAULT_FILE = _script_dir.parent / "bot" / "audio" / "privet-druzya.mp3"


def format_time(seconds: float) -> str:
    """Форматирует время в секундах в формат MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_with_timestamps(segments: list[dict]) -> str:
    """Форматирует сегменты с таймкодами."""
    parts = []
    for seg in segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        if text:
            parts.append(f"[{format_time(start)} → {format_time(end)}] {text}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Транскрибация локальных аудио/видео файлов через Whisper",
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
        default="medium",
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
        "--timestamps",
        action="store_true",
        help="Выводить результат с таймкодами по сегментам",
    )
    args = parser.parse_args()

    file_path = args.file.resolve()
    if not file_path.exists():
        print(f"Ошибка: файл не найден: {file_path}")
        raise SystemExit(1)

    result = _transcribe_audio_sync(
        str(file_path),
        model=args.model,
        language=args.language,
        device=args.device,
    )

    if args.timestamps and result["segments"]:
        print(format_with_timestamps(result["segments"]))
    else:
        print(result["text"])


if __name__ == "__main__":
    main()
