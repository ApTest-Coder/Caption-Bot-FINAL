"""Shared callback actions for navigation and channel settings."""

from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.types import InlineKeyboardMarkup

from utils.compat import button
from .context import (
    DB,
    main_menu,
    merged_config,
    public_access_cb,
    set_state,
    settings_menu,
)

router = Router()


async def edit_ui_message(message, text: str, reply_markup=None) -> None:
    """Edit either a normal text message or a media-caption message safely."""
    if any(
        (
            message.photo,
            message.video,
            message.audio,
            message.document,
            message.animation,
        )
    ):
        await message.edit_caption(
            caption=text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return
    await message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=reply_markup,
    )


@router.callback_query(F.data == "home")
async def home(query) -> None:
    """Return to the main menu."""
    if not await public_access_cb(query):
        return
    await edit_ui_message(query.message, "🤖 <b>Auto Caption Bot</b>", main_menu())
    await query.answer()


@router.callback_query(F.data == "help")
async def help_menu(query) -> None:
    """Show help from the inline menu."""
    if not await public_access_cb(query):
        return
    await edit_ui_message(
        query.message,
        "Use /channels to add and configure channels.",
        main_menu(),
    )
    await query.answer()


@router.callback_query(F.data == "settings")
async def settings_menu_callback(query) -> None:
    """Open the settings entry point."""
    if not await public_access_cb(query):
        return
    await edit_ui_message(
        query.message,
        "⚙️ Select a channel from /channels.",
        main_menu(),
    )
    await query.answer()


@router.callback_query(F.data.startswith("set:"))
async def setting_callback(query) -> None:
    """Toggle boolean settings or start a validated text-input flow."""
    if not await public_access_cb(query):
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Invalid setting.", show_alert=True)
        return
    _, kind, raw_channel_id = parts
    try:
        channel_id = int(raw_channel_id)
    except ValueError:
        await query.answer("Invalid channel.", show_alert=True)
        return

    row = await DB.get_channel(channel_id)
    if not row or row["owner_id"] != query.from_user.id:
        await query.answer("Not your channel.", show_alert=True)
        return

    settings = merged_config(row)
    if kind == "media":
        settings["media_details"] = not settings["media_details"]
    elif kind == "stickers":
        if settings["stickers"].get("enabled"):
            settings["stickers"]["enabled"] = False
        else:
            set_state(
                query.from_user.id,
                {"type": "stickers", "channel_id": channel_id},
            )
            await edit_ui_message(
                query.message,
                "🎉 Send the sticker you want the bot to add after processed posts.\n\n/cancel",
            )
            await query.answer()
            return
    else:
        prompts = {
            "caption": "📝 Send caption template.",
            "buttons": "🔘 Button Text | URL | blue/green/red",
            "replace": "🔄 old text | new text",
            "filters": "🎯 video/audio/document/photo/animation/voice/sticker",
            "forward": "📤 Destination channel ID.",
            "prefix": "✨ Send prefix.",
            "suffix": "✨ Send suffix.",
        }
        prompt = prompts.get(kind)
        if prompt is None:
            await query.answer("Unknown setting.", show_alert=True)
            return
        set_state(query.from_user.id, {"type": kind, "channel_id": channel_id})
        await edit_ui_message(query.message, f"{prompt}\n\n/cancel")
        await query.answer()
        return

    await DB.save_channel(
        row["owner_id"],
        channel_id,
        row["title"],
        row.get("username", ""),
        json.dumps(settings, ensure_ascii=False),
    )
    await query.message.edit_reply_markup(
        reply_markup=settings_menu(channel_id, settings)
    )
    await query.answer()


@router.callback_query(F.data.startswith("remove:"))
async def remove_channel(query) -> None:
    """Remove a channel owned by the current user."""
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
    await DB.delete_channel(channel_id, query.from_user.id)
    await edit_ui_message(
        query.message,
        "🗑 Channel removed.",
        InlineKeyboardMarkup(
            inline_keyboard=[
                [button(text="↩️ Channels", callback_data="channels", color="blue")]
            ]
        ),
    )
    await query.answer()
