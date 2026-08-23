"""Multi-channel management and per-channel settings input."""

from __future__ import annotations

import json
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message

from database.settings import default_settings
from .buttons import normalize_button, validate_button
from .callbacks import edit_ui_message
from .context import (
    DB,
    LOGGER,
    channel_menu,
    clear_state,
    get_state,
    merged_config,
    public_access,
    public_access_cb,
    report_error,
    set_state,
    settings_menu,
)
from .filters import validate_filter
from .forward import parse_destination
from .replace import validate_rule

router = Router()

#: Ceilings that keep a single channel's settings blob (and its keyboard) within
#: what Telegram will accept and what the database row can reasonably hold.
MAX_BUTTONS = 20
MAX_REPLACEMENTS = 50

ADMIN_STATUSES = {"administrator", "creator"}


@router.message(Command("channels"))
async def channels_command(message: Message) -> None:
    """List connected channels in private chat."""
    if message.chat.type != "private" or not await public_access(message):
        return
    rows = await DB.list_channels(message.from_user.id)
    await message.answer(
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        parse_mode="HTML",
        reply_markup=channel_menu(rows),
    )


@router.callback_query(F.data == "channels")
async def channels_callback(query) -> None:
    """Open the connected-channel selector."""
    if not await public_access_cb(query):
        return
    rows = await DB.list_channels(query.from_user.id)
    await edit_ui_message(
        query.message,
        f"📺 <b>Channels</b>\n\nConnected: <b>{len(rows)}</b>",
        channel_menu(rows),
    )
    await query.answer()


@router.callback_query(F.data == "add_channel")
async def add_channel_callback(query) -> None:
    """Start the add-channel flow."""
    if not await public_access_cb(query):
        return
    set_state(query.from_user.id, {"type": "channel"})
    await edit_ui_message(
        query.message,
        "➕ <b>Add Channel</b>\n\n"
        "Send the Channel ID or forward a message directly from that channel.\n"
        "Both you and the bot must be administrators there.\n\n/cancel",
    )
    await query.answer()


@router.callback_query(F.data.startswith("ch:"))
async def channel_callback(query) -> None:
    """Open one channel's settings panel."""
    if not await public_access_cb(query):
        return
    try:
        channel_id = int(query.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Invalid channel.", show_alert=True)
        return
    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return
    title = escape(str(row.get("title") or "Channel"), quote=False)
    username = escape(str(row.get("username") or "private"), quote=False)
    await edit_ui_message(
        query.message,
        f"📄 <b>{title}</b>\n"
        f"🆔 <code>{channel_id}</code>\n"
        f"🔗 @{username}",
        settings_menu(channel_id, merged_config(row)),
    )
    await query.answer()


@router.message(Command("cancel"))
async def cancel(message: Message) -> None:
    """Cancel a pending channel/settings input."""
    clear_state(message.from_user.id)
    await message.answer("❌ Cancelled.")


@router.message(F.chat.type == "private")
async def private_input(message: Message) -> None:
    """Consume validated values for channel and setting prompts."""
    state = get_state(message.from_user.id)
    if not state:
        return

    try:
        if state["type"] == "channel":
            origin = getattr(getattr(message, "forward_origin", None), "chat", None)
            if origin is None:
                raw_id = (message.text or "").strip()
                if not raw_id or not raw_id.lstrip("-").isdigit():
                    await message.answer(
                        "❌ Send a numeric Channel ID or forward a message directly from a channel."
                    )
                    return
                channel_id = int(raw_id)
            else:
                if origin.type != "channel":
                    await message.answer(
                        "❌ Please forward a message directly from a channel."
                    )
                    return
                channel_id = origin.id

            existing = await DB.get_channel(channel_id)
            if existing and existing["owner_id"] != message.from_user.id:
                await message.answer(
                    "❌ This channel is already managed by another user."
                )
                return

            # The bot must be an administrator to edit posts...
            me = await message.bot.get_me()
            bot_member = await message.bot.get_chat_member(channel_id, me.id)
            if bot_member.status not in ADMIN_STATUSES:
                await message.answer("❌ Bot must be an administrator in the channel.")
                return

            # ...and the *requesting user* must be one too. Without this check
            # any user who can guess or read a channel ID could claim a channel
            # the bot administers and rewrite its captions and buttons, because
            # ownership was granted purely on a first-come basis.
            try:
                user_member = await message.bot.get_chat_member(
                    channel_id, message.from_user.id
                )
            except TelegramAPIError as exc:
                LOGGER.info(
                    "Add-channel rejected for user %s on %s: %s",
                    message.from_user.id,
                    channel_id,
                    exc,
                )
                await message.answer(
                    "❌ Could not verify your permissions in that channel. "
                    "Make sure you are an administrator there and try again."
                )
                return
            if user_member.status not in ADMIN_STATUSES:
                await message.answer(
                    "❌ You must be an administrator of that channel to add it."
                )
                return

            chat = await message.bot.get_chat(channel_id)
            settings = default_settings()
            await DB.save_channel(
                message.from_user.id,
                channel_id,
                chat.title or "Channel",
                chat.username or "",
                json.dumps(settings, ensure_ascii=False),
            )
            clear_state(message.from_user.id)
            await message.answer(
                f"✅ <b>{escape(str(chat.title or 'Channel'), quote=False)}</b> added.",
                parse_mode="HTML",
                reply_markup=settings_menu(channel_id, settings),
            )
            return

        channel_id = int(state["channel_id"])
        row = await DB.get_channel(channel_id)
        if not row or row["owner_id"] != message.from_user.id:
            clear_state(message.from_user.id)
            await message.answer("❌ Channel configuration was not found.")
            return

        settings = merged_config(row)
        text = (message.text or message.caption or "").strip()
        kind = state["type"]

        if kind == "caption":
            settings["caption"] = text
        elif kind in {"prefix", "suffix"}:
            settings[kind] = text
        elif kind == "replace":
            parts = text.split("|", 1)
            if len(parts) != 2:
                await message.answer("Use: old text | new text")
                return
            valid, reason = validate_rule(parts[0], parts[1])
            if not valid:
                await message.answer(f"❌ {reason}")
                return
            if (
                len(settings["replacements"]) >= MAX_REPLACEMENTS
                and parts[0].strip() not in settings["replacements"]
            ):
                await message.answer(
                    f"❌ Replacement limit reached ({MAX_REPLACEMENTS})."
                )
                return
            settings["replacements"][parts[0].strip()] = parts[1].strip()
        elif kind == "buttons":
            parts = [item.strip() for item in text.split("|")]
            if len(parts) != 3:
                await message.answer("Use: Button Text | URL | blue/green/red")
                return
            valid, reason = validate_button(parts[0], parts[1], parts[2])
            if not valid:
                await message.answer(f"❌ {reason}")
                return
            if len(settings["buttons"]) >= MAX_BUTTONS:
                await message.answer(f"❌ Button limit reached ({MAX_BUTTONS}).")
                return
            settings["buttons"].append(
                normalize_button(parts[0], parts[1], parts[2])
            )
        elif kind == "forward":
            destination = parse_destination(text, source_id=channel_id)
            if destination is None:
                await message.answer(
                    "❌ Send a numeric channel ID that is different from this channel."
                )
                return
            settings["forward"] = {"enabled": True, "destination": destination}
        elif kind == "filters":
            valid, reason = validate_filter(text)
            if not valid:
                await message.answer(f"❌ {reason}")
                return
            settings["filters"] = {"type": text.lower().strip()}
        elif kind == "stickers":
            if not message.sticker:
                await message.answer("❌ Please send a Telegram sticker.")
                return
            settings["stickers"] = {
                "enabled": True,
                "file_id": message.sticker.file_id,
            }
        else:
            clear_state(message.from_user.id)
            await message.answer("❌ Unknown configuration request. Try again.")
            return

        await DB.save_channel(
            row["owner_id"],
            channel_id,
            row["title"],
            row.get("username", ""),
            json.dumps(settings, ensure_ascii=False),
        )
        clear_state(message.from_user.id)
        await message.answer(
            "✅ Saved.",
            reply_markup=settings_menu(channel_id, settings),
        )
    except (ValueError, TypeError):
        # Kept as a user-friendly fallback, but logged with a traceback: this
        # branch previously swallowed genuine bugs without leaving any trace.
        clear_state(message.from_user.id)
        LOGGER.exception(
            "Rejected settings input from user %s (state=%r)",
            message.from_user.id,
            state,
        )
        await message.answer(
            "❌ Invalid value. Please check the format and try again."
        )
    except Exception as exc:
        clear_state(message.from_user.id)
        await report_error(message.bot, message, exc)
