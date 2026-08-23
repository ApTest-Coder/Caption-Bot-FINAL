"""Compatibility layer for optional / version-dependent aiogram API surface.

Why this module exists
---------------------
The original code did ``from aiogram.enums import ButtonStyle`` at import time
and passed ``style=`` to every :class:`InlineKeyboardButton`. If the installed
aiogram does not export ``ButtonStyle`` that import raises ``ImportError``,
which propagates through ``plugins.context`` into *every* plugin and prevents
the bot from starting at all.

Colored inline keyboard buttons are not part of the classic Telegram Bot API
``InlineKeyboardButton`` definition, so this capability must be treated as
optional rather than assumed. Two independent conditions are checked:

1. ``aiogram.enums.ButtonStyle`` can be imported.
2. ``style`` is a *declared* field on ``InlineKeyboardButton``.

Condition 2 matters because aiogram's models are pydantic models configured
with ``extra="allow"``. That means ``InlineKeyboardButton(style=...)`` would be
accepted silently and then serialized into the outgoing API request even when
Telegram does not understand the field. ``model_fields`` only ever contains
*declared* fields, so it is the reliable capability probe.

The result is code that renders styled buttons when the running stack genuinely
supports them and plain buttons otherwise, without ever failing at import.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton

try:  # pragma: no cover - depends on the installed aiogram version
    from aiogram.enums import ButtonStyle as _ButtonStyle
except ImportError:  # pragma: no cover
    _ButtonStyle = None


def _style_field_declared() -> bool:
    """Return True only when ``style`` is a declared InlineKeyboardButton field."""
    fields = getattr(InlineKeyboardButton, "model_fields", None)
    try:
        return bool(fields) and "style" in fields
    except TypeError:  # pragma: no cover - defensive
        return False


BUTTON_STYLE_SUPPORTED = _ButtonStyle is not None and _style_field_declared()

#: User-facing colour name -> attribute name on ``ButtonStyle``.
_COLOR_TO_STYLE_NAME = {
    "blue": "PRIMARY",
    "primary": "PRIMARY",
    "green": "SUCCESS",
    "success": "SUCCESS",
    "red": "DANGER",
    "danger": "DANGER",
}

#: Colour names accepted from users when configuring buttons.
SUPPORTED_COLORS = ("blue", "green", "red")


def resolve_style(color: str | None):
    """Return the ``ButtonStyle`` member for *color*, or None when unsupported.

    Returns None whenever button styles are unavailable, so callers can simply
    omit the field instead of branching.
    """
    if not BUTTON_STYLE_SUPPORTED:
        return None
    name = _COLOR_TO_STYLE_NAME.get((color or "blue").strip().lower(), "PRIMARY")
    return getattr(_ButtonStyle, name, None)


def button(text: str, *, color: str | None = None, **kwargs) -> InlineKeyboardButton:
    """Build an InlineKeyboardButton, applying *color* only when supported.

    ``style`` is never passed to aiogram unless it is a real declared field,
    which keeps unknown keys out of the Telegram API payload.
    """
    style = resolve_style(color)
    if style is not None:
        kwargs["style"] = style
    return InlineKeyboardButton(text=text, **kwargs)
