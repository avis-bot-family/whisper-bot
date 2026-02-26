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
    """Загружает аудио в формате для pyannote (16kHz mono) через системный ffmpeg."""
    import subprocess

    import numpy as np
    import torch

    cmd = [
        "ffmpeg", "-i", file_path,
        "-f", "s16le", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-v", "quiet", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, check=True)
    audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    waveform = torch.from_numpy(audio).unsqueeze(0)
    return {"waveform": waveform, "sample_rate": 16000}


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

    from transcribe_worker.transcribe import transcribe_audio_sync

    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        raise ValueError(
            "Для диаризации нужен HuggingFace токен. "
            "Установите HF_TOKEN в .env и примите условия: "
            "https://huggingface.co/pyannote/speaker-diarization-community-1"
        )

    logger.info("Запуск транскрибации Whisper...")
    whisper_result = transcribe_audio_sync(
        file_path,
        model=model,
        language=language,
        device=device,
    )

    logger.info("Запуск диаризации pyannote.audio...")
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

        audio_input = _load_audio_for_pyannote(file_path)
        diarization = pipeline(audio_input, **diarization_kwargs)

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
