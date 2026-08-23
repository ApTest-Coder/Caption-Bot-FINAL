"""About information and project attribution."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import PROJECT_CREDIT
from .context import public_access

router = Router()
ABOUT_TEXT = "Advanced lightweight Telegram Auto Caption Bot with multi-channel settings."


@router.message(Command("about"))
async def about(message: Message) -> None:
    """Show project information and credit."""
    if not await public_access(message):
        return
    await message.answer(
        f"ℹ️ <b>About</b>\n\n{ABOUT_TEXT}\n\nCredit: {PROJECT_CREDIT}",
        parse_mode="HTML",
    )
