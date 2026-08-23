"""Shared runtime context for feature plugins."""

from __future__ import annotations

import json
import logging
import os
import time
from html import escape
from urllib.parse import urlparse

from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

from config import ADMIN_USERNAME, FSUB_LINK, OWNER_ID, PUBLIC_MODE
from database.settings import Database, default_settings
from utils.compat import button

LOGGER = logging.getLogger("caption_bot")
DB = Database()
RUNTIME = {"processed": 0, "edited": 0, "failed": 0}
STATES: dict[int, dict] = {}
STARTED_AT = time.monotonic()

#: A pending prompt is abandoned after this long, so STATES cannot grow forever.
STATE_TTL_SECONDS = 15 * 60
#: Hard ceiling on concurrent pending prompts (defence against memory growth).
STATE_MAX_ENTRIES = 5000

#: Owner error reports are rate limited; a misconfigured channel would otherwise
#: generate one direct message per incoming post.
ERROR_REPORT_INTERVAL = 60.0
_LAST_ERROR_REPORT: dict[str, float] = {}

VALID_FILTERS = {
    "video",
    "audio",
    "document",
    "photo",
    "animation",
    "voice",
    "sticker",
}


def _purge_states(now: float) -> None:
    """Drop expired pending prompts."""
    stale = [
        user_id
        for user_id, state in STATES.items()
        if now - float(state.get("_ts", 0.0)) > STATE_TTL_SECONDS
    ]
    for user_id in stale:
        STATES.pop(user_id, None)


def set_state(user_id: int, state: dict) -> None:
    """Record a pending prompt for *user_id* with an expiry timestamp."""
    now = time.monotonic()
    _purge_states(now)
    if len(STATES) >= STATE_MAX_ENTRIES and user_id not in STATES:
        oldest = min(STATES, key=lambda key: STATES[key].get("_ts", 0.0))
        STATES.pop(oldest, None)
    STATES[user_id] = {**state, "_ts": now}


def get_state(user_id: int) -> dict | None:
    """Return the pending prompt for *user_id*, or None when absent/expired."""
    state = STATES.get(user_id)
    if state is None:
        return None
    if time.monotonic() - float(state.get("_ts", 0.0)) > STATE_TTL_SECONDS:
        STATES.pop(user_id, None)
        return None
    return state


def clear_state(user_id: int) -> None:
    """Forget any pending prompt for *user_id*."""
    STATES.pop(user_id, None)



def valid_http_url(value: str) -> bool:
    """Return True only for absolute HTTP(S) URLs."""
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _safe_settings(stored: object) -> dict:
    """Normalize persisted settings without letting corrupt data crash the UI."""
    base = default_settings()
    if not isinstance(stored, dict):
        return base

    buttons = stored.get("buttons")
    if isinstance(buttons, list):
        base["buttons"] = [
            item
            for item in buttons
            if isinstance(item, dict)
            and isinstance(item.get("text"), str)
            and isinstance(item.get("url"), str)
        ]

    replacements = stored.get("replacements")
    if isinstance(replacements, dict):
        base["replacements"] = {
            str(old): str(new)
            for old, new in replacements.items()
            if str(old).strip()
        }

    filters = stored.get("filters")
    if isinstance(filters, dict) and isinstance(filters.get("type"), str):
        filter_type = filters["type"].strip().lower()
        if filter_type in VALID_FILTERS:
            base["filters"] = {"type": filter_type}

    forward = stored.get("forward")
    if isinstance(forward, dict):
        enabled = forward.get("enabled")
        destination = forward.get("destination")
        if isinstance(enabled, bool):
            base["forward"]["enabled"] = enabled
        if isinstance(destination, int) and destination != 0:
            base["forward"]["destination"] = destination

    stickers = stored.get("stickers")
    if isinstance(stickers, dict):
        enabled = stickers.get("enabled")
        file_id = stickers.get("file_id")
        if isinstance(enabled, bool):
            base["stickers"]["enabled"] = enabled
        if isinstance(file_id, str) and file_id.strip():
            base["stickers"]["file_id"] = file_id.strip()

    for key in ("caption", "prefix", "suffix"):
        value = stored.get(key)
        if isinstance(value, str):
            base[key] = value

    media_details = stored.get("media_details")
    if isinstance(media_details, bool):
        base["media_details"] = media_details

    return base


def merged_config(row: dict) -> dict:
    """Merge persisted channel settings with safe current defaults."""
    try:
        stored = json.loads(row.get("config") or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        LOGGER.warning("Invalid settings JSON for channel %s", row.get("channel_id"))
        return default_settings()
    return _safe_settings(stored)


def uptime_text() -> str:
    """Return process uptime."""
    seconds = int(time.monotonic() - STARTED_AT)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m"


def has_media(message: Message) -> bool:
    """Return whether a post contains supported media."""
    return any(
        (
            message.video,
            message.audio,
            message.document,
            message.photo,
            message.animation,
            message.voice,
            message.sticker,
        )
    )


def media_matches_filter(message: Message, filters: dict) -> bool:
    """Check a channel's optional media-type filter."""
    if not isinstance(filters, dict):
        return True
    media_type = str(filters.get("type") or "").strip().lower()
    if not media_type:
        return True
    return bool(
        {
            "video": message.video,
            "audio": message.audio,
            "document": message.document,
            "photo": message.photo,
            "animation": message.animation,
            "voice": message.voice,
            "sticker": message.sticker,
        }.get(media_type)
    )


async def is_admin(user_id: int) -> bool:
    """Check owner or database administrators."""
    return user_id == OWNER_ID or await DB.is_admin(user_id)


async def private_notice(message: Message) -> None:
    """Send the configured private-mode notice."""
    await message.answer(
        "🔒 This Bot Is Private\n\n"
        f"Please contact the administrator. {ADMIN_USERNAME}"
    )


async def answer_with_photo(
    message: Message,
    path: str | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Reply with *path* as a photo when possible, otherwise with plain text.

    aiogram 3 requires an ``InputFile`` instance; handing it a raw file object
    raises a pydantic ``ValidationError``, which is **not** an ``OSError``. The
    original code only guarded ``OSError``, so configuring a start image made
    the command fail instead of degrading gracefully. Any send failure here is
    non-fatal: the text response still goes out.
    """
    if path and os.path.isfile(path):
        try:
            await message.answer_photo(
                FSInputFile(path),
                caption=text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return
        except Exception:
            LOGGER.exception("Could not send photo %s; falling back to text", path)
    await message.answer(text, reply_markup=reply_markup, parse_mode="HTML")


def main_menu() -> InlineKeyboardMarkup:
    """Build the common main menu."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(
                    text="📺 Channels",
                    callback_data="channels",
                    color="blue",
                ),
                button(
                    text="📊 Stats",
                    callback_data="stats",
                    color="green",
                ),
            ],
            [
                button(
                    text="⚙️ Settings",
                    callback_data="settings",
                    color="blue",
                ),
                button(
                    text="ℹ️ Help",
                    callback_data="help",
                    color="blue",
                ),
            ],
        ]
    )


def channel_menu(rows: list[dict]) -> InlineKeyboardMarkup:
    """Build the connected-channel selector."""
    keyboard = [
        [
            button(
                text=f"📢 {row.get('title', 'Channel')}",
                callback_data=f"ch:{row['channel_id']}",
                color="blue",
            )
        ]
        for row in rows[:40]
    ]
    keyboard.extend(
        [
            [
                button(
                    text="➕ Add New Channel",
                    callback_data="add_channel",
                    color="green",
                )
            ],
            [
                button(
                    text="↩️ Back",
                    callback_data="home",
                    color="blue",
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def settings_menu(channel_id: int, settings: dict) -> InlineKeyboardMarkup:
    """Build the per-channel settings panel."""
    safe = _safe_settings(settings)

    def state(value: bool) -> str:
        return "ON ✅" if value else "OFF ❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button(
                    text="📝 Caption",
                    callback_data=f"set:caption:{channel_id}",
                    color="blue",
                ),
                button(
                    text=f"🔘 Buttons ({len(safe['buttons'])})",
                    callback_data=f"set:buttons:{channel_id}",
                    color="green",
                ),
            ],
            [
                button(
                    text=f"🔄 Replace ({len(safe['replacements'])})",
                    callback_data=f"set:replace:{channel_id}",
                    color="blue",
                ),
                button(
                    text=f"🎯 Filters {state(bool(safe['filters']))}",
                    callback_data=f"set:filters:{channel_id}",
                    color="green",
                ),
            ],
            [
                button(
                    text=f"📤 Forward {state(safe['forward']['enabled'])}",
                    callback_data=f"set:forward:{channel_id}",
                    color="blue",
                ),
                button(
                    text=f"✨ Prefix {state(bool(safe['prefix']))}",
                    callback_data=f"set:prefix:{channel_id}",
                    color="green",
                ),
            ],
            [
                button(
                    text=f"✨ Suffix {state(bool(safe['suffix']))}",
                    callback_data=f"set:suffix:{channel_id}",
                    color="blue",
                ),
                button(
                    text=f"🎉 Stickers {state(safe['stickers']['enabled'])}",
                    callback_data=f"set:stickers:{channel_id}",
                    color="green",
                ),
            ],
            [
                button(
                    text=f"📊 Media Details {state(safe['media_details'])}",
                    callback_data=f"set:media:{channel_id}",
                    color="blue",
                )
            ],
            [
                button(
                    text="🗑 Remove",
                    callback_data=f"remove:{channel_id}",
                    color="red",
                ),
                button(
                    text="↩️ Back",
                    callback_data="channels",
                    color="blue",
                ),
            ],
        ]
    )


async def public_access(message: Message) -> bool:
    """Apply public/private mode and the force-subscribe gate."""
    await DB.user_upsert(message.from_user.id, message.from_user.username or "")
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
        return False

    from .fsub import require_membership, send_gate

    allowed, _ = await require_membership(message.bot, message.from_user.id)
    if allowed:
        return True
    if not valid_http_url(FSUB_LINK):
        await message.answer(
            "⚠️ Force-subscribe is temporarily unavailable. "
            "Please contact the administrator."
        )
        return False
    await send_gate(message)
    return False


async def public_access_cb(query) -> bool:
    """Apply public/private mode to inline callbacks."""
    await DB.user_upsert(query.from_user.id, query.from_user.username or "")
    if await is_admin(query.from_user.id):
        return True
    if not PUBLIC_MODE:
        await query.answer(
            "🔒 This Bot Is Private. "
            f"Contact the administrator {ADMIN_USERNAME}",
            show_alert=True,
        )
        return False

    from .fsub import require_membership, send_gate

    allowed, keyboard = await require_membership(query.bot, query.from_user.id)
    if allowed:
        return True
    if keyboard:
        await send_gate(query.message)
        await query.answer()
        return False
    await query.answer(
        "⚠️ Force-subscribe is temporarily unavailable.",
        show_alert=True,
    )
    return False


async def require_admin(message: Message) -> bool:
    """Allow only the owner or a stored admin."""
    if await is_admin(message.from_user.id):
        return True
    if not PUBLIC_MODE:
        await private_notice(message)
    else:
        await message.answer("❌ Admin only.")
    return False


async def require_owner(message: Message) -> bool:
    """Allow only the configured owner.

    Commands that change *who* is an administrator must be owner-only. Gating
    them on :func:`require_admin` let any existing admin promote further admins
    or demote their peers, so a single compromised or careless admin account
    could take over the bot's entire admin set.
    """
    if message.from_user.id == OWNER_ID:
        return True
    await message.answer("❌ Owner only.")
    return False


async def report_error(bot, message: Message, error: Exception) -> None:
    """Send unexpected processing errors to the owner, rate limited per cause.

    Without the rate limit a single misconfigured channel produces one owner
    direct message for every incoming post, which both floods the owner and
    burns the bot's send quota.
    """
    RUNTIME["failed"] += 1
    key = f"{getattr(message.chat, 'id', '?')}:{type(error).__name__}"
    now = time.monotonic()
    last = _LAST_ERROR_REPORT.get(key, 0.0)
    if last and now - last < ERROR_REPORT_INTERVAL:
        LOGGER.warning("Suppressed duplicate error report for %s: %s", key, error)
        return
    if len(_LAST_ERROR_REPORT) > 1000:
        _LAST_ERROR_REPORT.clear()
    _LAST_ERROR_REPORT[key] = now

    LOGGER.error("Processing error in %s: %s", key, error, exc_info=error)
    try:
        await bot.send_message(
            OWNER_ID,
            "<b>🚨 Caption Bot Error</b>\n\n"
            f"<b>Channel:</b> {escape(str(message.chat.title or message.chat.id))}\n"
            f"<b>Message:</b> {message.message_id}\n"
            f"<blockquote expandable><b>Reason:</b> {escape(str(error)[:3000])}</blockquote>",
            parse_mode="HTML",
        )
    except Exception:
        LOGGER.exception("Could not deliver owner error report")
