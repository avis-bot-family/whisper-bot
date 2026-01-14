from aiogram import Router

from bot.handlers.info import router as info_router
from bot.handlers.transcribe import router as transcribe_router


def get_handlers_router() -> Router:
    router = Router()
    router.include_router(info_router)
    router.include_router(transcribe_router)
    return router
