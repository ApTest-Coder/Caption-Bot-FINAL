"""Text replacement rules used by channel caption processing."""


def validate_rule(old: str, new: str) -> tuple[bool, str]:
    """Validate one replacement pair before it is persisted."""
    if not old.strip():
        return False, "Old text cannot be empty."
    return True, ""


def apply(text: str, rules: dict | None) -> str:
    """Apply configured string replacements in order."""
    for old, new in (rules or {}).items():
        text = text.replace(old, new)
    return text
