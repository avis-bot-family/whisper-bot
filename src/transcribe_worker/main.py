import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from transcribe_worker.diarize import transcribe_with_diarization_sync
from transcribe_worker.settings import settings
from transcribe_worker.transcribe import transcribe_audio_sync

app = FastAPI(title="Transcribe Worker", version="0.1.0")


class TranscribeRequest(BaseModel):
    file_path: str
    model: str = settings.MODEL
    language: str = settings.LANGUAGE


class TranscribeDiarizeRequest(BaseModel):
    file_path: str
    model: str = settings.MODEL
    language: str = settings.LANGUAGE
    hf_token: str | None = None
    num_speakers: int | None = None
    min_speakers: int | None = settings.DIARIZE_MIN_SPEAKERS
    max_speakers: int | None = settings.DIARIZE_MAX_SPEAKERS


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/transcribe")
async def transcribe(req: TranscribeRequest) -> dict:
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=404, detail=f"Файл не найден: {req.file_path}")

    logger.info(f"POST /transcribe file_path={req.file_path} model={req.model}")
    try:
        result = await asyncio.to_thread(
            transcribe_audio_sync,
            req.file_path,
            model=req.model,
            language=req.language,
            device=settings.DEVICE,
        )
        return result
    except Exception as e:
        logger.error(f"Ошибка транскрибации: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe-diarize")
async def transcribe_diarize(req: TranscribeDiarizeRequest) -> dict:
    if not Path(req.file_path).exists():
        raise HTTPException(status_code=404, detail=f"Файл не найден: {req.file_path}")

    hf_token = req.hf_token or settings.HF_TOKEN
    if not hf_token:
        raise HTTPException(
            status_code=400,
            detail="HF_TOKEN не указан. Необходим для диаризации.",
        )

    logger.info(f"POST /transcribe-diarize file_path={req.file_path} model={req.model}")
    try:
        result = await asyncio.to_thread(
            transcribe_with_diarization_sync,
            req.file_path,
            model=req.model,
            language=req.language,
            device=settings.DEVICE,
            hf_token=hf_token,
            num_speakers=req.num_speakers,
            min_speakers=req.min_speakers,
            max_speakers=req.max_speakers,
        )
        return result
    except Exception as e:
        logger.error(f"Ошибка диаризации: {e}")
        raise HTTPException(status_code=500, detail=str(e))
