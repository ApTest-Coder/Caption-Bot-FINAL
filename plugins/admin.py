"""Owner and administrator commands."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import OWNER_ID
from .context import DB, require_admin, require_owner

router = Router()


def _parse_user_id(text: str | None) -> int | None:
    """Extract a numeric Telegram user ID from a command's argument."""
    parts = (text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    raw = parts[1].strip()
    if not raw.lstrip("-").isdigit():
        return None
    return int(raw)


@router.message(Command("addadmin"))
async def add_admin(message: Message) -> None:
    """Add a stored administrator by numeric Telegram ID (owner only)."""
    if not await require_owner(message):
        return
    user_id = _parse_user_id(message.text)
    if user_id is None or user_id <= 0:
        await message.answer("Usage: /addadmin USER_ID")
        return
    await DB.add_admin(user_id)
    await message.answer("✅ Admin added.")


@router.message(Command("deladmin"))
async def delete_admin(message: Message) -> None:
    """Remove a stored administrator; the owner is protected (owner only)."""
    if not await require_owner(message):
        return
    user_id = _parse_user_id(message.text)
    if user_id is None or user_id <= 0:
        await message.answer("Usage: /deladmin USER_ID")
        return
    if user_id == OWNER_ID:
        # The owner is derived from config, so removing the row would not revoke
        # access -- but it would leave a misleading database state.
        await message.answer("❌ The owner cannot be removed.")
        return
    await DB.del_admin(user_id)
    await message.answer("✅ Admin removed.")


@router.message(Command("set_public"))
async def set_public(message: Message) -> None:
    """Explain the deployment-level public mode setting."""
    if await require_admin(message):
        await message.answer(
            "Set PUBLIC_MODE in the environment (or .env) and restart the bot."
        )
