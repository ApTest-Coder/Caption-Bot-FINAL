"""Button validation and rendering helpers."""

from utils.compat import SUPPORTED_COLORS
from .context import valid_http_url

#: Single source of truth for the accepted colour names, shared with the
#: keyboard builder so validation and rendering can never drift apart.
COLORS = SUPPORTED_COLORS

#: Telegram truncates very long button labels; reject them up front instead.
MAX_BUTTON_TEXT = 64


def validate_button(text: str, url: str, color: str) -> tuple[bool, str]:
    """Validate a user-created URL button."""
    if not text.strip():
        return False, "Button text cannot be empty."
    if len(text.strip()) > MAX_BUTTON_TEXT:
        return False, f"Button text must be at most {MAX_BUTTON_TEXT} characters."
    if not valid_http_url(url):
        return False, "Button URL must start with http:// or https://"
    if color.lower() not in COLORS:
        return False, "Button color must be blue, green or red."
    return True, ""


def normalize_button(text: str, url: str, color: str) -> dict:
    """Return the canonical database representation of a button."""
    return {
        "text": text.strip(),
        "url": url.strip(),
        "color": color.strip().lower(),
    }
