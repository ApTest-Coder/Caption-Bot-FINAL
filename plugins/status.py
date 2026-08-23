"""Runtime and database statistics."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from .callbacks import edit_ui_message
from .context import DB, RUNTIME, main_menu, public_access, public_access_cb, uptime_text

router = Router()


def status_text(counts: dict[str, int]) -> str:
    """Format the status panel in one place for commands and callbacks."""
    return (
        "📊 <b>Bot Status</b>\n\n"
        f"👥 Users: {counts['users']}\n"
        f"📺 Channels: {counts['channels']}\n\n"
        f"📥 Processed: {RUNTIME['processed']}\n"
        f"✅ Edited: {RUNTIME['edited']}\n"
        f"❌ Errors: {RUNTIME['failed']}\n"
        f"⏱ Uptime: {uptime_text()}"
    )


@router.message(Command("stats"))
async def stats_command(message: Message) -> None:
    """Show users, channels and runtime counters."""
    if not await public_access(message):
        return
    await message.answer(status_text(await DB.counts()), parse_mode="HTML")


@router.callback_query(F.data == "stats")
async def stats_callback(query) -> None:
    """Show statistics from the main menu."""
    if not await public_access_cb(query):
        return
    await edit_ui_message(
        query.message,
        status_text(await DB.counts()),
        main_menu(),
    )
    await query.answer()
