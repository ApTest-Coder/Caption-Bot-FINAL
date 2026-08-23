"""Deployment configuration for Caption Bot, loaded from the environment.

Every value is read from an environment variable, optionally seeded from a local
``.env`` file (which is git-ignored). Nothing secret is stored in this tracked
module: the previous version held the credentials themselves, and because
``config.py`` is tracked while ``.gitignore`` only excluded ``config.local.py``
and ``config.secret.py``, following the setup instructions meant committing a
live bot token.

Copy ``.env.example`` to ``.env`` and fill it in. See :func:`validate` for the
startup checks that turn a misconfiguration into a clear error instead of a
confusing runtime failure.

The ``.env`` parser is deliberately tiny and dependency-free -- ``KEY=value``
lines, ``#`` comments, and optional surrounding quotes -- so that deployments
that already inject real environment variables need nothing extra installed.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path: Path = ENV_FILE) -> None:
    """Seed os.environ from *path* without overriding real env vars."""
    if not path.is_file():
        return
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()


def _str(name: str, default: str = "") -> str:
    """Read a string setting."""
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _int(name: str, default: int = 0) -> int:
    """Read an integer setting, falling back to *default* on bad input."""
    raw = _str(name)
    if not raw or not raw.lstrip("-").isdigit():
        return default
    return int(raw)


def _bool(name: str, default: bool = False) -> bool:
    """Read a boolean setting from common truthy/falsey spellings."""
    raw = _str(name).lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


# Telegram application
BOT_TOKEN = _str("8755911972:AAGveMA6jmyzoulY2pK-9X77YI9-uwgHktY")
API_ID = _int("37005781")
API_HASH = _str("3a83e09c4c18a66906dacac2bb0df64a")
OWNER_ID = _int("8251423077")

# Access & channels
PUBLIC_MODE = _bool("PUBLIC_MODE", True)
ADMIN_USERNAME = _str("ADMIN_USERNAME", "@ApLover")
MAIN_CHANNEL = _str("@Leech_kro")
FSUB_CHANNEL = _str("-1002237499389")
FSUB_LINK = _str("https://t.me/Leech_kro")

# Assets & diagnostics
START_PIC = _str("START_PIC", "https://graph.org/file/c4abf29ae8a885c1d6211-f3e55ad0362141467a.png")
FSUB_PIC = _str("FSUB_PIC", "https://graph.org/file/c4abf29ae8a885c1d6211-f3e55ad0362141467a.png")
LOG_CHANNEL = _int("-1003260715044")

# Storage
DATABASE_TYPE = _str("DATABASE_TYPE", "sqlite").lower()  # mongodb | sqlite
MONGO_URI = _str("mongodb+srv://Caption:Biswas1236@autocaptionbot.km6fvlv.mongodb.net/?appName=AutoCaptionBot")
DATABASE_NAME = _str("DATABASE_NAME", "caption_bot")
SQLITE_DATABASE = _str("SQLITE_DATABASE", "data/bot.db")

# Project attribution
PROJECT_CREDIT = _str("PROJECT_CREDIT", "https://t.me/Ap_Lover_S_B")

SUPPORTED_DATABASES = ("mongodb", "sqlite")


def validate() -> list[str]:
    """Return a list of configuration problems, empty when the config is usable.

    Called at startup so that a missing token fails immediately with an
    actionable message, rather than surfacing later as an opaque Telegram
    "Unauthorized" response.
    """
    problems: list[str] = []
    if not BOT_TOKEN:
        problems.append("BOT_TOKEN is not set (get one from @BotFather).")
    elif ":" not in BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN":
        problems.append("BOT_TOKEN does not look like a real token.")
    if OWNER_ID <= 0:
        problems.append("OWNER_ID must be your numeric Telegram user ID.")
    if DATABASE_TYPE not in SUPPORTED_DATABASES:
        problems.append(
            f"DATABASE_TYPE must be one of {', '.join(SUPPORTED_DATABASES)}."
        )
    if DATABASE_TYPE == "mongodb" and not MONGO_URI:
        problems.append("MONGO_URI is required when DATABASE_TYPE=mongodb.")
    if FSUB_CHANNEL and not FSUB_LINK:
        problems.append(
            "FSUB_LINK is required when FSUB_CHANNEL is set, "
            "otherwise users cannot pass the join gate."
        )
    return problems
