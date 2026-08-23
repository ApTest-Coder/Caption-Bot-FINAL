"""Caption template rendering and dynamic variable expansion."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from html import escape

from .parser import media_values, parse_filename

TOKEN_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
SPECIAL_FALLBACKS = {
    "episode": "E01 - E0?",
    "season": "S01 - S0?",
    "quality": "Unknown Quality",
    "audio": "Audio",
}

HTML_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|tg-spoiler)"
    r"(?:\s[^>]*)?>",
    re.IGNORECASE,
)

#: Telegram hard limits. Media captions are far shorter than text messages.
#: Both limits are counted *after* entity parsing, i.e. against the visible
#: text, so measuring the HTML string against them is deliberately conservative.
CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096

#: Tags Telegram's HTML parse mode understands. Anything else is left alone
#: rather than guessed at, so a stray ``<`` cannot invent a closing tag.
_BALANCED_TAGS = frozenset(
    {
        "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
        "span", "tg-spoiler", "a", "code", "pre", "blockquote",
    }
)
_TAG_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)(?:\s[^<>]*)?>")
_PARTIAL_ENTITY_RE = re.compile(r"&#?[A-Za-z0-9]{0,8}$")


def human_size(value: int | float | None) -> str | None:
    """Convert a byte count to a compact human-readable value."""
    if value is None:
        return None
    size = float(value)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {units[index]}"


def human_duration(value: int | float | None) -> str | None:
    """Convert seconds to a human-readable duration."""
    if value is None:
        return None
    return str(timedelta(seconds=int(value)))


def strip_html(value: str) -> str:
    """Remove supported Telegram HTML tags without destroying plain text."""
    return HTML_TAG_RE.sub("", value)


def _wish() -> str:
    """Return a greeting based on the local process time."""
    hour = datetime.now().hour
    if hour < 12:
        return "Good Morning"
    if hour < 17:
        return "Good Afternoon"
    return "Good Evening"


def _escape_dynamic(value: object) -> str:
    """Escape dynamic metadata before it is inserted into Telegram HTML."""
    return escape(str(value), quote=False)


def source_html(message) -> str:
    """Return the source caption/text rendered as Telegram-safe HTML.

    aiogram exposes ``Message.html_text`` as a *property* that raises
    ``TypeError`` when the message carries neither text nor caption. A bare
    ``getattr(message, "html_text", None)`` cannot suppress that, because
    ``getattr`` only swallows ``AttributeError`` -- the exception escapes from
    inside the property body. Uncaptioned media is the single most common input
    for an auto-caption bot, so this must be handled explicitly.

    Returns an empty string when there is no source text at all, which lets
    callers distinguish "nothing to preserve" from "preserved markup".
    """
    original = getattr(message, "caption", None) or getattr(message, "text", None) or ""
    if not original:
        return ""

    try:
        rendered = message.html_text
    except (TypeError, AttributeError):
        rendered = None
    if isinstance(rendered, str) and rendered:
        return rendered

    # No entity-rendered form available: escape so the caller's HTML parse mode
    # cannot be broken by a literal '<' or '&' in the source text.
    return escape(original, quote=False)


def _unclosed_tags(fragment: str) -> str:
    """Return the closing tags needed to balance *fragment*."""
    stack: list[str] = []
    for match in _TAG_RE.finditer(fragment):
        closing, name = match.group(1), match.group(2).lower()
        if name not in _BALANCED_TAGS:
            continue
        if not closing:
            stack.append(name)
        elif name in stack:
            while stack:
                if stack.pop() == name:
                    break
    return "".join(f"</{name}>" for name in reversed(stack))


def clamp(value: str, limit: int) -> str:
    """Trim *value* to *limit* characters, leaving valid Telegram HTML behind.

    Telegram rejects over-long captions with a 400 error, but a naive cut causes
    a *different* 400 (``Can't parse entities``) in three ways, all of which are
    handled here:

    * the cut lands inside a tag, leaving ``<b`` -- pull back before the ``<``;
    * the cut lands inside an entity, leaving ``&am`` -- pull back before the
      ``&``, otherwise the fragment renders as literal garbage;
    * the cut lands inside an *element*, leaving ``<b>text`` with no ``</b>``.
      The bot wraps captions in ``<blockquote expandable>``, so this is the
      common case rather than an edge case.

    Missing closing tags are appended rather than having the content dropped:
    Telegram counts the limit *after* entity parsing, so closing tags cost
    nothing against it, and dropping content back to the opening tag of a
    wrapped caption would discard the whole caption.
    """
    if limit <= 0 or len(value) <= limit:
        return value

    cut = value[:limit]

    open_at = cut.rfind("<")
    if open_at != -1 and cut.find(">", open_at) == -1:
        cut = cut[:open_at]

    cut = _PARTIAL_ENTITY_RE.sub("", cut)
    cut = cut.rstrip()

    return cut + _unclosed_tags(cut)


def format_caption(template: str, message) -> str:
    """Render a caption while safely handling unavailable media metadata."""
    original = getattr(message, "caption", None) or getattr(message, "text", None) or ""
    values = media_values(message)
    filename = values.get("filename") or ""

    parsed = parse_filename(filename)
    caption_parsed = parse_filename(original)
    for key in ("episode", "season", "quality", "year", "language", "audio"):
        if not parsed.get(key):
            parsed[key] = caption_parsed.get(key)
    values.update(parsed)

    values["caption"] = strip_html(original)
    values["html_caption"] = source_html(message)
    values["ext"] = filename.rsplit(".", 1)[-1] if "." in filename else None
    values["resolution"] = (
        f"{values['width']}x{values['height']}"
        if values.get("width") and values.get("height")
        else None
    )
    values["filesize"] = human_size(values.get("filesize"))
    values["duration"] = human_duration(values.get("duration"))
    values["wish"] = _wish()

    for key, fallback in SPECIAL_FALLBACKS.items():
        values[key] = values.get(key) or fallback

    lines: list[str] = []
    for line in template.splitlines():
        tokens = TOKEN_RE.findall(line)
        if tokens and any(
            token not in SPECIAL_FALLBACKS and not values.get(token)
            for token in tokens
        ):
            continue
        lines.append(line)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key)
        if value is None:
            return ""
        if key == "html_caption":
            return str(value)
        return _escape_dynamic(value)

    rendered = TOKEN_RE.sub(replace, "\n".join(lines))
    return "\n".join(line.rstrip() for line in rendered.splitlines()).strip()
