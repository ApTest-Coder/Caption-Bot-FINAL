"""Owner-only broadcast delivery with FloodWait and blocked-user handling."""

import asyncio
import logging

from aiogram import Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import Message

from .context import DB, require_admin

LOGGER = logging.getLogger("caption_bot.broadcast")
router = Router()

#: How often to refresh the progress message during a long broadcast.
PROGRESS_EVERY = 25


async def deliver(bot, user_id: int, source: Message, text: str) -> str:
    """Deliver one broadcast item and return its result category."""
    for attempt in range(2):
        try:
            if source.reply_to_message:
                await bot.copy_message(
                    user_id,
                    source.chat.id,
                    source.reply_to_message.message_id,
                )
            else:
                await bot.send_message(user_id, text, parse_mode="HTML")
            return "sent"
        except TelegramRetryAfter as exc:
            if attempt:
                return "failed"
            await asyncio.sleep(exc.retry_after)
        except TelegramForbiddenError:
            await DB.mark_blocked(user_id)
            return "blocked"
        except Exception:
            LOGGER.exception("Broadcast delivery failed for %s", user_id)
            return "failed"
    return "failed"


@router.message(Command("broadcast"))
async def broadcast(message: Message) -> None:
    """Broadcast text or a replied-to Telegram message to tracked users.

    Delivery is sequential and paced: Telegram rate limits bulk sends hard, and
    a burst of concurrent requests just converts into FloodWait. Progress is
    reported periodically so a large run does not look hung.
    """
    if not await require_admin(message):
        return
    body = (message.text or "").split(maxsplit=1)
    text = body[1].strip() if len(body) > 1 else ""
    if not message.reply_to_message and not text:
        await message.answer(
            "Usage: reply to a message with /broadcast, or /broadcast <text>."
        )
        return

    user_ids = await DB.user_ids()
    if not user_ids:
        await message.answer("No users to broadcast to yet.")
        return

    total = len(user_ids)
    status = await message.answer(f"📤 Broadcasting to {total} users…")
    sent = blocked = failed = 0
    for index, user_id in enumerate(user_ids, start=1):
        result = await deliver(message.bot, user_id, message, text)
        if result == "sent":
            sent += 1
        elif result == "blocked":
            blocked += 1
        else:
            failed += 1
        if index % PROGRESS_EVERY == 0 and index != total:
            try:
                await status.edit_text(
                    f"📤 Broadcasting… {index}/{total}\n"
                    f"✅ {sent} · 🚫 {blocked} · ❌ {failed}"
                )
            except Exception:
                # A failed progress update must never abort the broadcast.
                LOGGER.debug("Could not update broadcast progress", exc_info=True)
        await asyncio.sleep(0.05)

    summary = (
        "✅ <b>Broadcast complete</b>\n\n"
        f"👥 Total: {total}\n"
        f"✅ Sent: {sent}\n"
        f"🚫 Blocked: {blocked}\n"
        f"❌ Failed: {failed}"
    )
    try:
        await status.edit_text(summary, parse_mode="HTML")
    except Exception:
        LOGGER.warning("Could not edit broadcast summary; sending a new message")
        await message.answer(summary, parse_mode="HTML")
