"""Application entry point for Auto Caption Bot.

Feature handlers live in ``plugins/``. This module only wires the application,
storage and routers together and starts long polling.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher

import config
from config import BOT_TOKEN
from plugins.about import router as about_router
from plugins.admin import router as admin_router
from plugins.broadcast import router as broadcast_router
from plugins.callbacks import router as callback_router
from plugins.caption import router as caption_router
from plugins.channels import router as channels_router
from plugins.context import DB
from plugins.help import router as help_router
from plugins.start import router as start_router
from plugins.status import router as status_router
from plugins.users import router as users_router
from utils.logger import setup as setup_logging

LOGGER = logging.getLogger("caption_bot")


def build_dispatcher() -> Dispatcher:
    """Create the dispatcher and register feature routers."""
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    dispatcher.include_router(help_router)
    dispatcher.include_router(about_router)
    dispatcher.include_router(status_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(broadcast_router)
    dispatcher.include_router(users_router)
    dispatcher.include_router(channels_router)
    dispatcher.include_router(callback_router)
    dispatcher.include_router(caption_router)
    return dispatcher


async def main() -> None:
    """Validate configuration, initialize storage and start long polling."""
    setup_logging()

    # Fail fast and loudly: without this the bot starts, connects, and then
    # every Telegram call fails with an opaque "Unauthorized".
    problems = config.validate()
    if problems:
        LOGGER.error("Configuration is incomplete:")
        for problem in problems:
            LOGGER.error("  - %s", problem)
        LOGGER.error("Copy .env.example to .env and fill in the required values.")
        raise SystemExit(1)

    await DB.connect()
    bot = Bot(BOT_TOKEN)
    dispatcher = build_dispatcher()
    LOGGER.info("Caption Bot starting")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await DB.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl-C is a normal way to stop a long-polling bot; don't dump a
        # traceback for it.
        LOGGER.info("Caption Bot stopped")
    except SystemExit as exc:
        sys.exit(exc.code)
