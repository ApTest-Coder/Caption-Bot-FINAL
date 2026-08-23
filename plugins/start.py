"""Start and settings entry points."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from config import START_PIC
from .context import answer_with_photo, main_menu, public_access

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    """Show the welcome screen."""
    if not await public_access(message):
        return
    text = (
        "👋 <b>Welcome to Auto Caption Bot</b>\n\n"
        "⚡ Multi-channel • Smart Caption • Colored Buttons"
    )
    await answer_with_photo(message, START_PIC, text, main_menu())


@router.message(Command("settings"))
async def settings_command(message: Message) -> None:
    """Open the settings entry point."""
    if await public_access(message):
        await message.answer(
            "⚙️ Select a channel from /channels.",
            reply_markup=main_menu(),
        )
