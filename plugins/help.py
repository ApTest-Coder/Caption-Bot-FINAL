"""Public help command and help text."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .context import public_access

router = Router()
HELP_TEXT = (
    "<b>Help</b>\n\n"
    "Use /channels to add and configure channels.\n"
    "Every channel has independent settings."
)


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    """Show the public help entry point."""
    if await public_access(message):
        await message.answer(HELP_TEXT, parse_mode="HTML")
