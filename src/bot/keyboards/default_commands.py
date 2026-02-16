from __future__ import annotations
from typing import TYPE_CHECKING

from aiogram.types import BotCommand, BotCommandScopeDefault

if TYPE_CHECKING:
    from aiogram import Bot

users_commands = [
    ("start", "🚀 Начать работу с ботом"),
    ("help", "ℹ️ Справка и информация о боте"),
    ("transcribe", "🎙️ Транскрибация аудио/видео"),
    ("transcribe_diarize", "👥 Транскрибация со спикерами"),
]


async def set_default_commands(bot: Bot) -> None:
    await remove_default_commands(bot)
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in users_commands],
        scope=BotCommandScopeDefault(),
    )


async def remove_default_commands(bot: Bot) -> None:
    await bot.delete_my_commands(scope=BotCommandScopeDefault())
