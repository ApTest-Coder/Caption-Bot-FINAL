"""Supported media filters for per-channel processing."""

MEDIA_TYPES = (
    "video",
    "audio",
    "document",
    "photo",
    "animation",
    "voice",
    "sticker",
)


def validate_filter(value: str) -> tuple[bool, str]:
    """Validate a media type before saving it to channel settings."""
    normalized = value.strip().lower()
    if normalized not in MEDIA_TYPES:
        return False, "Valid: video/audio/document/photo/animation/voice/sticker"
    return True, ""


def matches(message, media_type: str) -> bool:
    """Return whether a Telegram message contains the requested media type."""
    return bool(
        {
            "video": message.video,
            "audio": message.audio,
            "document": message.document,
            "photo": message.photo,
            "animation": message.animation,
            "voice": message.voice,
            "sticker": message.sticker,
        }.get(media_type.strip().lower())
    )
