"""Per-channel forward/copy helpers."""

from __future__ import annotations

import asyncio

from aiogram.exceptions import TelegramRetryAfter


def parse_destination(value: str, source_id: int | None = None) -> int | None:
    """Parse a Telegram channel/chat ID, including negative ``-100...`` IDs.

    When *source_id* is supplied, a destination equal to it is rejected. A
    channel that copies its own posts back into itself creates a new
    ``channel_post`` update, which the bot processes and copies again -- an
    unbounded amplification loop that only stops when Telegram rate limits the
    bot. Blocking the self-reference is the only place this can be caught
    cheaply, before it is ever persisted.
    """
    value = (value or "").strip()
    if not value or not value.lstrip("-").isdigit():
        return None
    destination = int(value)
    if destination == 0:
        return None
    if source_id is not None and destination == source_id:
        return None
    return destination


async def copy_with_retry(
    bot,
    destination: int,
    message,
    attempts: int = 2,
) -> None:
    """Copy a channel post with bounded FloodWait retry."""
    if destination == 0:
        raise ValueError("Forward destination cannot be zero")
    if destination == message.chat.id:
        # Defence in depth: settings written by an older version (or edited
        # directly in the database) could still hold a self-reference.
        raise ValueError("Forward destination cannot be the source channel")
    attempts = max(1, min(attempts, 3))
    for attempt in range(attempts):
        try:
            await bot.copy_message(
                destination,
                message.chat.id,
                message.message_id,
            )
            return
        except TelegramRetryAfter as exc:
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(exc.retry_after)
