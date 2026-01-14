"""Lifecycle hooks для бота (startup/shutdown)."""

from loguru import logger

from bot.core.loader import bot, dp
from bot.handlers import get_handlers_router
from bot.keyboards.default_commands import remove_default_commands, set_default_commands
from bot.middlewares import register_middlewares
from bot.settings import Settings
from bot.utils.transcribe import transcribe_audio

settings = Settings()


async def on_startup() -> None:
    """Обработчик запуска бота."""
    logger.info("bot starting...")

    register_middlewares(dp)

    dp.include_router(get_handlers_router())

    await set_default_commands(bot)

    bot_info = await bot.get_me()

    logger.info(f"Name     - {bot_info.full_name}")
    logger.info(f"Username - @{bot_info.username}")
    logger.info(f"ID       - {bot_info.id}")

    states: dict[bool | None, str] = {
        True: "Enabled",
        False: "Disabled",
        None: "Unknown (This's not a bot)",
    }

    logger.info(f"Groups Mode  - {states[bot_info.can_join_groups]}")
    logger.info(f"Privacy Mode - {states[not bot_info.can_read_all_group_messages]}")
    logger.info(f"Inline Mode  - {states[bot_info.supports_inline_queries]}")

    if settings.webhook.USE_WEBHOOK:
        logger.info("=" * 50)
        logger.info("Bot работает через WEBHOOK")
        logger.info(f"Webhook URL  - {settings.webhook.webhook_url}")
        logger.info(f"Webhook Host - {settings.webhook.HOST}")
        logger.info(f"Webhook Port - {settings.webhook.PORT}")
        logger.info(f"Webhook Path - {settings.webhook.PATH}")
        logger.info("=" * 50)
    else:
        logger.info("Bot работает через POLLING")

    # Транскрибация при старте, если включена
    if settings.transcribe.ENABLE_ON_STARTUP:
        await run_startup_transcribe()

    logger.info("bot started")


async def run_startup_transcribe() -> None:
    """Запускает транскрибацию файла при старте бота, если включена в настройках."""
    audio_file_path = settings.transcribe.AUDIO_FILE_PATH

    if not audio_file_path:
        logger.warning(
            "Транскрибация при старте включена, но файл не указан. Проверьте настройку transcribe_AUDIO_FILE_PATH"
        )
        return

    logger.info("=" * 50)
    logger.info("Запуск транскрибации при старте бота")
    logger.info(f"Файл: {audio_file_path}")
    logger.info("=" * 50)

    try:
        transcribed_text = await transcribe_audio(
            file_path=audio_file_path,
            model=settings.transcribe.MODEL,
            language=settings.transcribe.LANGUAGE,
            device=settings.transcribe.DEVICE,
        )

        logger.info("=" * 50)
        logger.info("РЕЗУЛЬТАТ ТРАНСКРИБАЦИИ:")
        logger.info("=" * 50)
        logger.info(transcribed_text)
        logger.info("=" * 50)

    except Exception as e:
        logger.error(f"Ошибка при транскрибации при старте: {e}")


async def on_shutdown() -> None:
    """Обработчик остановки бота."""
    logger.info("bot stopping...")

    await remove_default_commands(bot)

    await dp.storage.close()
    await dp.fsm.storage.close()

    await bot.delete_webhook()
    await bot.session.close()

    logger.info("bot stopped")
