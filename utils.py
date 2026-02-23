# utils.py
import re
import unicodedata
from typing import Any, Sequence


def norm_text(s: str) -> str:
    """Lowercase, strip, remove accents, collapse spaces, drop punctuation."""
    if not s:
        return ""
    s = s.strip().lower()
    s = "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_code(s: str) -> str:
    """Extract letters only and uppercase (good for ISO codes)."""
    if not s:
        return ""
    return re.sub(r"[^A-Za-z]+", "", s).upper()


def safe_first(lst: Sequence[Any]):
    return lst[0] if lst else None


def parse_population_strict(raw: str):
    """
    Strict numeric parsing:
    Accepts digits with optional commas/spaces. Rejects anything else.
    """
    if raw is None:
        return None
    s = raw.strip().replace(",", "").replace(" ", "")
    if not s or not s.isdigit():
        return None
    if len(s) > 15:
        return None
    return int(s)