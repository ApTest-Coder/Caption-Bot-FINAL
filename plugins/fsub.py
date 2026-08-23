"""Force-subscribe membership checks and public join UI."""

from __future__ import annotations

from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from config import FSUB_CHANNEL, FSUB_LINK, FSUB_PIC
from utils.compat import button
from .context import LOGGER, answer_with_photo, valid_http_url

#: Statuses that mean the user is currently inside the channel. ``restricted``
#: members are still members unless Telegram reports ``is_member=False``.
JOINED_STATUSES = {"creator", "administrator", "member"}

#: Substrings in Telegram's error text that indicate the *bot* or the *channel*
#: is misconfigured rather than the user being absent.
_CONFIG_ERROR_HINTS = (
    "chat not found",
    "bot is not a member",
    "member list is inaccessible",
    "not enough rights",
    "chat_id is empty",
    "bot was kicked",
)


def join_keyboard() -> InlineKeyboardMarkup | None:
    """Return a public Join button only when its URL is valid."""
    if not valid_http_url(FSUB_LINK):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [button(text="📢 Join Channel", url=FSUB_LINK, color="green")]
        ]
    )


def _is_joined(member) -> bool:
    """Interpret a ChatMember, treating joined-but-restricted users as members."""
    status = str(getattr(member, "status", "") or "").lower()
    if status in JOINED_STATUSES:
        return True
    if status == "restricted":
        # A restricted member is still in the chat unless explicitly flagged.
        return getattr(member, "is_member", True) is not False
    return False


async def is_member(bot, user_id: int) -> bool:
    """Check membership using only the configured public channel target.

    Failure handling is deliberately asymmetric. Force-subscribe is a growth
    gate, not a security boundary, so a *configuration* fault (wrong channel ID,
    bot removed from the channel) must not lock every user out of the bot with
    no way to recover. Those cases fail open and log loudly. A genuine
    "user not found" answer means the user really is not a member, so it denies.
    """
    if not FSUB_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FSUB_CHANNEL, user_id)
    except TelegramAPIError as exc:
        text = str(exc).lower()
        if "user not found" in text or "user_id_invalid" in text:
            return False
        if any(hint in text for hint in _CONFIG_ERROR_HINTS):
            LOGGER.error(
                "FSUB is misconfigured for channel %r (%s); allowing access so "
                "the bot stays usable. Fix FSUB_CHANNEL or re-add the bot.",
                FSUB_CHANNEL,
                exc,
            )
            return True
        LOGGER.exception("Unexpected FSUB membership failure; allowing access")
        return True
    except Exception:
        LOGGER.exception("Unexpected FSUB membership failure; allowing access")
        return True
    return _is_joined(member)


async def require_membership(bot, user_id: int) -> tuple[bool, InlineKeyboardMarkup | None]:
    """Return membership state and a public join keyboard when required."""
    if await is_member(bot, user_id):
        return True, None
    return False, join_keyboard()


async def send_gate(message) -> None:
    """Send the FSUB gate with the configured photo when available."""
    await answer_with_photo(
        message,
        FSUB_PIC,
        "🔒 <b>Join Required</b>\n\nPlease join our channel to use this bot.",
        join_keyboard(),
    )
