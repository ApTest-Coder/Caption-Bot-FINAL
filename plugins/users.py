"""User tracking helpers and owner user-management commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from .context import DB, require_admin

router = Router()


async def track(message: Message) -> None:
    """Refresh the user's activity record."""
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")


@router.message(Command("users"))
async def users_command(message: Message) -> None:
    """Show the tracked-user count to administrators."""
    if not await require_admin(message):
        return
    counts = await DB.counts()
    await message.answer(f"👥 Total users: {counts['users']}")
