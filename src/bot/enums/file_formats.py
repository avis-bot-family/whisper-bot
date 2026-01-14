"""Поддерживаемые форматы файлов для транскрибации."""

from enum import Enum


class AudioFormat(str, Enum):
    """Поддерживаемые аудио форматы."""

    OGG = "ogg"
    MP3 = "mp3"
    WAV = "wav"
    M4A = "m4a"
    FLAC = "flac"
    AAC = "aac"


class VideoFormat(str, Enum):
    """Поддерживаемые видео форматы."""

    MP4 = "mp4"
    MKV = "mkv"
    AVI = "avi"
    MOV = "mov"
    WEBM = "webm"
    FLV = "flv"


class FileType(str, Enum):
    """Типы файлов для обработки."""

    VOICE = "voice"
    AUDIO = "audio"
    VIDEO = "video"
    VIDEO_NOTE = "video_note"
