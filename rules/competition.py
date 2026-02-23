# rules/competition.py

import re
from utils import norm_text


NAME_ALLOWED_RE = re.compile(r"^[A-Za-z0-9 '\-]+$")

# Keep this list small and explicit. Expand cautiously.
PROFANITY = {
    "fuck",
    "shit",
    "cunt",
    "bitch",
    "wanker",
    "twat",
}


_WS_RE = re.compile(r"\s+")

def normalize_player_name(name_raw: str) -> str:
    """Strip ends and collapse internal whitespace to single spaces."""
    return _WS_RE.sub(" ", (name_raw or "").strip())


def validate_player_name(name_raw: str) -> tuple[bool, str]:
    """
    Returns (ok, error_message).

    Rules:
    - Minimum 3 alphabetic letters
    - Allowed characters: letters, numbers, space, apostrophe, hyphen
    - Basic profanity filter
    """
    if not name_raw:
        return False, "Please enter a name."

    name = normalize_player_name(name_raw)
    if not name:
        return False, "Please enter a name."

    if len(name) > 24:
        return False, "Name is too long (max 24 characters)."

    if not NAME_ALLOWED_RE.match(name):
        return False, "Name can only contain letters, numbers, spaces, apostrophes, and hyphens."

    # Require at least 3 alphabetic letters
    letter_count = sum(1 for ch in name if ch.isalpha())
    if letter_count < 3:
        return False, "Name must include at least 3 letters."

    # Profanity check (normalized)
    n = norm_text(name)
    if any(bad in n for bad in PROFANITY):
        return False, "Please choose a different name."

    return True, ""


def is_complete_country(fields: dict) -> bool:
    """
    Competition mode only: require all four Qs to be present.
    """
    return (
        bool(fields.get("capital"))
        and isinstance(fields.get("population"), int)
        and fields.get("population") > 0
        and bool(fields.get("languages"))
        and bool(fields.get("currencies"))
    )