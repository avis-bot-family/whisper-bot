"""
Диаризация спикеров: объединение Whisper (ASR) и pyannote.audio (speaker diarization).

Требования:
- HuggingFace токен с принятыми условиями:
  - pyannote/speaker-diarization-community-1
  - https://huggingface.co/pyannote/speaker-diarization-community-1
"""

from __future__ import annotations

import os
import warnings
from typing import Any

from loguru import logger


def _assign_speaker_to_segment(
    seg_start: float,
    seg_end: float,
    diarization_turns: list[dict],
) -> str:
    """Назначает спикера сегменту по максимальному перекрытию по времени."""
    speaker_overlap: dict[str, float] = {}
    for turn in diarization_turns:
        start, end = turn["start"], turn["end"]
        speaker = turn.get("speaker", "SPEAKER_00")
        overlap_start = max(seg_start, start)
        overlap_end = min(seg_end, end)
        overlap = max(0, overlap_end - overlap_start)
        speaker_overlap[speaker] = speaker_overlap.get(speaker, 0) + overlap

    if not speaker_overlap:
        return "SPEAKER_00"
    return max(speaker_overlap, key=speaker_overlap.get)


def _load_audio_for_pyannote(file_path: str) -> dict:
    """Загружает аудио в формате для pyannote (16kHz mono), обходя torchcodec."""
    import torch
    import torchaudio
    import torchaudio.functional as F_audio

    waveform, sample_rate = torchaudio.load(file_path)
    # Моно: усредняем каналы
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    # Ресемплинг в 16 kHz
    if sample_rate != 16000:
        waveform = F_audio.resample(waveform, sample_rate, 16000)
        sample_rate = 16000
    return {"waveform": waveform, "sample_rate": sample_rate}


def align_whisper_with_diarization(
    whisper_segments: list[dict],
    diarization_segments: list[dict],
) -> list[dict]:
    """Сопоставляет сегменты Whisper с результатами диаризации.

    Args:
        whisper_segments: [{"start", "end", "text"}, ...]
        diarization_segments: [{"start", "end", "speaker"}, ...]

    Returns:
        [{"start", "end", "text", "speaker"}, ...]
    """
    result = []
    for seg in whisper_segments:
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue
        speaker = _assign_speaker_to_segment(start, end, diarization_segments)
        result.append({
            "start": start,
            "end": end,
            "text": text,
            "speaker": speaker,
        })
    return result


def transcribe_with_diarization_sync(
    file_path: str,
    *,
    model: str = "small",
    language: str = "Russian",
    device: str = "cpu",
    hf_token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Транскрибация с диаризацией спикеров (Whisper + pyannote.audio 4.x).

    Возвращает словарь:
    - "text": полный текст
    - "segments": [{"start", "end", "text", "speaker"}, ...]
    """
    import torch

    from bot.utils.transcribe import _transcribe_audio_sync

    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise ValueError(
            "Для диаризации нужен HuggingFace токен. "
            "Установите HF_TOKEN в .env и примите условия: "
            "https://huggingface.co/pyannote/speaker-diarization-community-1"
        )

    logger.info("Запуск транскрибации Whisper...")
    whisper_result = _transcribe_audio_sync(
        file_path,
        model=model,
        language=language,
        device=device,
    )

    logger.info("Запуск диаризации pyannote.audio...")
    # Подавляем предупреждения torchcodec/FFmpeg и TF32 (аудио загружаем вручную)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-community-1",
            token=token,
        )
        if device == "cuda" and torch.cuda.is_available():
            try:
                pipeline.to(torch.device("cuda"))
            except torch.cuda.OutOfMemoryError:
                logger.warning(
                    "CUDA OOM при диаризации (GPU занят?). Используется CPU."
                )
                torch.cuda.empty_cache()

        diarization_kwargs: dict[str, Any] = {}
        if num_speakers is not None:
            diarization_kwargs["num_speakers"] = num_speakers
        if min_speakers is not None:
            diarization_kwargs["min_speakers"] = min_speakers
        if max_speakers is not None:
            diarization_kwargs["max_speakers"] = max_speakers

        # Загружаем аудио вручную — обход torchcodec/FFmpeg (libavutil.so)
        audio_input = _load_audio_for_pyannote(file_path)
        diarization = pipeline(audio_input, **diarization_kwargs)

    # pyannote 4.x: speaker_diarization -> (turn, speaker)
    diarization_segments = []
    for turn, speaker in diarization.speaker_diarization:
        diarization_segments.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": str(speaker),
        })

    segments_with_speakers = align_whisper_with_diarization(
        whisper_result["segments"],
        diarization_segments,
    )

    full_text = " ".join(s["text"] for s in segments_with_speakers)
    logger.info(f"Диаризация завершена. Сегментов: {len(segments_with_speakers)}")

    return {
        "text": full_text,
        "segments": segments_with_speakers,
    }


async def transcribe_with_diarization(
    file_path: str,
    *,
    model: str = "small",
    language: str = "Russian",
    device: str = "cpu",
    hf_token: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Асинхронная обёртка для транскрибации с диаризацией."""
    import asyncio

    return await asyncio.to_thread(
        transcribe_with_diarization_sync,
        file_path,
        model=model,
        language=language,
        device=device,
        hf_token=hf_token,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
