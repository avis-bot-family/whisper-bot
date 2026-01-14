"""Настройка webhook для бота."""

import asyncio

from loguru import logger

from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp.web import AppRunner, TCPSite

from bot.core.loader import app, bot, dp
from bot.settings import Settings

settings = Settings()


async def setup_webhook() -> None:
    """Настраивает и запускает webhook сервер."""
    logger.info("Настройка webhook...")

    await bot.set_webhook(
        settings.webhook.webhook_url,
        allowed_updates=dp.resolve_used_update_types(),
        secret_token=settings.webhook.SECRET,
    )

    logger.info(f"Webhook установлен: {settings.webhook.webhook_url}")

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook.SECRET,
    )
    webhook_requests_handler.register(app, path=settings.webhook.PATH)
    setup_application(app, dp, bot=bot)

    runner = AppRunner(app)
    await runner.setup()
    site = TCPSite(runner, host=settings.webhook.HOST, port=settings.webhook.PORT)
    await site.start()

    logger.info(f"Webhook сервер запущен на {settings.webhook.HOST}:{settings.webhook.PORT}")
    logger.info("Ожидание входящих запросов через webhook...")

    await asyncio.Event().wait()
