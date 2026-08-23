"""Filename and Telegram media metadata parsing."""

from __future__ import annotations

import re

RES_RE = re.compile(
    r"(?<!\d)(\d{3,4})[pP](?!\w)|\b(\d{3,4})[xX](\d{3,4})\b"
)
EP_RE = re.compile(
    r"(?i)(?:S\d{1,2}[ ._-]*)?E(?:P(?:ISODE)?)?[ ._-]*(\d{1,4})"
    r"|(?:EP(?:ISODE)?|E)[ ._-]*(\d{1,4})"
)
SEASON_RE = re.compile(r"(?i)\bS(?:EASON)?[ ._-]?(\d{1,2})(?!\d)")
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
LANGS = (
    "Hindi",
    "English",
    "Japanese",
    "Tamil",
    "Telugu",
    "Bengali",
    "Korean",
    "Chinese",
    "Arabic",
    "French",
    "Spanish",
    "German",
)


def parse_filename(name: str) -> dict[str, str | None]:
    """Extract episode, season, quality, year and language information."""
    text = name or ""
    result: dict[str, str | None] = {
        "episode": None,
        "season": None,
        "quality": None,
        "year": None,
        "language": None,
        "audio": None,
    }

    match = EP_RE.search(text)
    if match:
        result["episode"] = match.group(1) or match.group(2)

    match = SEASON_RE.search(text)
    if match:
        result["season"] = match.group(1)

    match = RES_RE.search(text)
    if match:
        result["quality"] = (
            f"{match.group(1)}p"
            if match.group(1)
            else f"{match.group(3)}p"
        )

    match = YEAR_RE.search(text)
    if match:
        result["year"] = match.group(1)

    lower = text.lower()
    result["language"] = next(
        (language for language in LANGS if language.lower() in lower),
        None,
    )
    # Audio is a language track when one can be inferred from the filename.
    # Keep the generic "Audio" fallback in the formatter when nothing is found.
    result["audio"] = result["language"]
    return result


def media_values(message) -> dict:
    """Extract metadata from supported Telegram media objects."""
    values: dict = {}
    if message.video:
        media = message.video
        values.update(
            filename=media.file_name,
            filesize=media.file_size,
            duration=media.duration,
            width=media.width,
            height=media.height,
            mime_type=media.mime_type,
        )
    elif message.audio:
        media = message.audio
        values.update(
            filename=media.file_name,
            filesize=media.file_size,
            duration=media.duration,
            title=media.title,
            artist=media.performer,
            mime_type=media.mime_type,
        )
    elif message.document:
        media = message.document
        values.update(
            filename=media.file_name,
            filesize=media.file_size,
            mime_type=media.mime_type,
        )
    elif message.photo:
        media = message.photo[-1]
        values.update(
            filesize=media.file_size,
            width=media.width,
            height=media.height,
            mime_type="image/jpeg",
        )
    elif message.animation:
        media = message.animation
        values.update(
            filename=media.file_name,
            filesize=media.file_size,
            duration=media.duration,
            width=media.width,
            height=media.height,
            mime_type=media.mime_type,
        )
    elif message.voice:
        media = message.voice
        values.update(
            filesize=media.file_size,
            duration=media.duration,
            mime_type=media.mime_type,
        )
    return {
        key: value
        for key, value in values.items()
        if value is not None
    }
