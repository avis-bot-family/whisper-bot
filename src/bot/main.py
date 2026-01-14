"""
withenv ./.env poetry run python3 ./src/bot/main.py
"""

import asyncio

from bot.core.loader import bot, dp
from bot.lifecycle import on_shutdown, on_startup
from bot.settings import Settings
from bot.webhook import setup_webhook

settings = Settings()


async def main() -> None:
    """Главная функция запуска бота."""
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.webhook.USE_WEBHOOK:
        await setup_webhook()
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
