"""Channel-post caption editing pipeline."""

from __future__ import annotations

import asyncio
import re
from html import escape, unescape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, ReplyParameters

from utils.compat import button
from utils.formatter import (
    CAPTION_LIMIT,
    clamp,
    format_caption,
    human_duration,
    human_size,
    source_html,
)
from utils.parser import media_values
from .context import (
    DB,
    RUNTIME,
    has_media,
    media_matches_filter,
    merged_config,
    report_error,
    valid_http_url,
)
from .forward import copy_with_retry

router = Router()
HTML_PART_RE = re.compile(r"(<[^>]+>)")

#: Telegram rejects keyboards larger than 100 buttons.
MAX_BUTTONS = 100


def source_caption_html(message) -> str:
    """Return Telegram-safe HTML for an unchanged source caption.

    Delegates to :func:`utils.formatter.source_html` so that the "what did the
    user originally post" question has exactly one answer in the codebase. The
    previous local implementation escaped the plain caption unconditionally,
    which silently destroyed the poster's own bold/italic/link formatting
    whenever no caption template was configured.
    """
    return source_html(message)


def apply_replacements(caption: str, rules: dict[str, str]) -> str:
    """Replace visible caption text without modifying HTML tags/entities."""
    if not rules:
        return caption

    chunks = HTML_PART_RE.split(caption)
    for index, chunk in enumerate(chunks):
        if not chunk or (chunk.startswith("<") and chunk.endswith(">")):
            continue
        text = unescape(chunk)
        for old, new in rules.items():
            text = text.replace(old, new)
        chunks[index] = escape(text, quote=False)
    return "".join(chunks)


def _is_not_modified(exc: Exception) -> bool:
    """Return True for Telegram's benign "message is not modified" rejection."""
    return "not modified" in str(exc).lower()


async def _with_flood_retry(action, attempts: int = 2):
    """Run *action* with bounded FloodWait retry, tolerating no-op edits.

    "message is not modified" is not an error condition for this bot: it simply
    means the computed caption already matches what Telegram stores. Treating it
    as a failure previously produced a spurious owner error report per post.
    """
    for attempt in range(attempts):
        try:
            return await action()
        except TelegramRetryAfter as exc:
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(exc.retry_after)
        except TelegramBadRequest as exc:
            if _is_not_modified(exc):
                return None
            raise
    return None


async def edit_caption(
    bot,
    message,
    caption: str,
    markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Edit caption and keyboard in a single API call.

    Doing this as two calls (caption, then markup) meant the first call stripped
    any existing keyboard and the second re-added it, so subscribers saw the
    buttons flicker, the bot burned two requests per post against Telegram's
    rate limit, and the ``edited`` counter was incremented twice.
    """
    await _with_flood_retry(
        lambda: bot.edit_message_caption(
            chat_id=message.chat.id,
            message_id=message.message_id,
            caption=caption or None,
            parse_mode="HTML",
            reply_markup=markup,
        )
    )


async def edit_markup(bot, message, markup: InlineKeyboardMarkup) -> None:
    """Edit only reply markup, including on sticker messages."""
    await _with_flood_retry(
        lambda: bot.edit_message_reply_markup(
            chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=markup,
        )
    )


def build_markup(buttons: list[dict]) -> InlineKeyboardMarkup | None:
    """Build two-column coloured URL buttons from stored settings."""
    valid = [
        button(text=item["text"], url=item["url"], color=item.get("color"))
        for item in buttons
        if item.get("text") and valid_http_url(item.get("url", ""))
    ][:MAX_BUTTONS]
    if not valid:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[valid[index : index + 2] for index in range(0, len(valid), 2)]
    )


def supports_caption_edit(message) -> bool:
    """Return whether the Telegram media type supports caption editing."""
    return any(
        (
            message.video,
            message.audio,
            message.document,
            message.photo,
            message.animation,
        )
    )


def media_details_caption(message) -> str:
    """Build a compact metadata block for the optional Media Details setting."""
    values = media_values(message)
    parts: list[str] = []
    size = human_size(values.get("filesize"))
    duration = human_duration(values.get("duration"))
    width = values.get("width")
    height = values.get("height")
    mime_type = values.get("mime_type")

    if size:
        parts.append(f"• Size: {escape(size)}")
    if duration:
        parts.append(f"• Duration: {escape(duration)}")
    if width and height:
        parts.append(f"• Resolution: {escape(str(width))}x{escape(str(height))}")
    if mime_type:
        parts.append(f"• MIME: {escape(str(mime_type))}")
    if not parts:
        return ""
    return (
        "<blockquote expandable>📊 <b>Media Details</b>\n"
        + "\n".join(parts)
        + "</blockquote>"
    )


def safe_plain_text(value: str) -> str:
    """Escape user-entered caption fragments before Telegram HTML parsing."""
    return escape(value, quote=False)


@router.channel_post()
async def process_channel_post(message) -> None:
    """Apply the selected channel's caption and button configuration."""
    row = await DB.get_channel(message.chat.id)
    if not row or not has_media(message):
        return
    settings = merged_config(row)
    if not media_matches_filter(message, settings["filters"]):
        return

    RUNTIME["processed"] += 1
    try:
        caption = (
            format_caption(settings["caption"], message)
            if settings["caption"]
            else source_caption_html(message)
        )
        caption = apply_replacements(caption, settings["replacements"])
        if settings["prefix"]:
            prefix = safe_plain_text(settings["prefix"])
            caption = f"{prefix}\n{caption}" if caption else prefix
        if settings["suffix"]:
            suffix = safe_plain_text(settings["suffix"])
            caption = f"{caption}\n{suffix}" if caption else suffix
        if settings["media_details"]:
            details = media_details_caption(message)
            if details:
                caption = f"{caption}\n{details}" if caption else details

        markup = build_markup(settings["buttons"])
        original_caption = source_caption_html(message)
        # Telegram rejects captions over 1024 characters with a 400 error, which
        # previously surfaced as an owner error report for every single post.
        caption = clamp(caption, CAPTION_LIMIT)
        if supports_caption_edit(message):
            if caption != original_caption:
                await edit_caption(message.bot, message, caption, markup)
                RUNTIME["edited"] += 1
            elif markup:
                await edit_markup(message.bot, message, markup)
                RUNTIME["edited"] += 1
        elif markup:
            await edit_markup(message.bot, message, markup)
            RUNTIME["edited"] += 1

        sticker = settings["stickers"]
        if sticker.get("enabled") and sticker.get("file_id"):
            await message.bot.send_sticker(
                chat_id=message.chat.id,
                sticker=sticker["file_id"],
                reply_parameters=ReplyParameters(message_id=message.message_id),
            )

        forward = settings["forward"]
        destination = forward.get("destination")
        if forward.get("enabled") and destination and destination != message.chat.id:
            await copy_with_retry(message.bot, destination, message)
    except Exception as exc:
        await report_error(message.bot, message, exc)
