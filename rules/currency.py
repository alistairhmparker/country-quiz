# currency_rules.py
from __future__ import annotations

from typing import Dict, List, Optional, Set

from utils import norm_code, norm_text

# Curated aliases for special cases (keep this tight and explicit).
# Note: "cfa franc" handled here, so no separate multiword-core mechanism needed.
EXTRA_CURRENCY_ALIASES_BY_CODE: Dict[str, Set[str]] = {
    "USD": {"us dollar", "u s dollar"},
    "GBP": {"pound sterling", "sterling", "pound"},
    "EUR": {"euro"},
    "JPY": {"yen"},
    "CNY": {"yuan", "renminbi", "rmb"},
    "KRW": {"won"},
    "INR": {"rupee"},
    "RUB": {"ruble", "rouble"},
    "PLN": {"zloty"},
    # CFA francs
    "XAF": {"cfa franc", "central african cfa franc", "cfa"},
    "XOF": {"cfa franc", "west african cfa franc", "cfa"},
}

# Bare-word meanings that must NOT apply globally.
# Example: "dollar" alone should mean USD, not any dollar.
BARE_WORD_DEFAULT_CODE: Dict[str, str] = {
    "dollar": "USD",
}

# Currency words for which we require a descriptor unless it's the default code.
# Today this is just {"dollar"} but keeping it as a set makes it easy to extend.
TYPE_WORDS_REQUIRE_DESCRIPTOR: Set[str] = set(BARE_WORD_DEFAULT_CODE.keys())

# Common currency symbols for crude detection (so we compare raw symbol).
_SYMBOL_CHARS = set("€£$¥₩₽₹₺₫₦₱₲₴₡₸₵₭₮₪₨")


def _core_aliases_from_official_name(code_u: str, official_name: str) -> Set[str]:
    """
    Default rule:
      - accept the last word of the official name (descriptor stripped)
        e.g. "azerbaijani manat" -> "manat"

    Special for type-words that require descriptor (e.g. "dollar"):
      - if code is the default meaning, accept bare word ("dollar" -> USD)
      - otherwise accept descriptor+type suffixes like "australian dollar"
    """
    name_n = norm_text(official_name)
    if not name_n:
        return set()

    toks = name_n.split()
    if not toks:
        return set()

    last = toks[-1]

    # e.g. "dollar" rule
    if last in TYPE_WORDS_REQUIRE_DESCRIPTOR:
        out: Set[str] = set()
        default_code = BARE_WORD_DEFAULT_CODE.get(last)

        if default_code and code_u == default_code:
            out.add(last)

        # allow suffixes ending in "dollar" (descriptor required)
        for n in (2, 3, 4):
            if len(toks) >= n:
                out.add(" ".join(toks[-n:]))
        return out

    # default: accept last word
    return {last}


def currency_aliases(
    code: str, name: str, symbol: Optional[str], single_currency_country: bool
) -> Set[str]:
    """
    Build acceptable aliases for one currency:
      - ISO code always accepted
      - official name accepted (normalized)
      - curated aliases
      - core alias (usually last word), with exclusions like "dollar"
      - symbol only if single-currency-country
    """
    code_u = (code or "").upper()
    aliases: Set[str] = set()

    if code_u:
        aliases.add(code_u)

    name_n = norm_text(name)
    if name_n:
        aliases.add(name_n)

    for a in EXTRA_CURRENCY_ALIASES_BY_CODE.get(code_u, set()):
        aliases.add(norm_text(a))

    if name:
        aliases |= _core_aliases_from_official_name(code_u, name)

    if single_currency_country and symbol:
        aliases.add(symbol.strip())

    return aliases


def currency_guess_is_correct(guess_raw: str, currency_objects: List[dict]) -> bool:
    """
    Determine if the guess matches any currency:
      - ISO code match is strongest
      - special: bare "dollar" means USD only
      - otherwise compare against aliases
      - symbol match only if single-currency-country
    """
    if not guess_raw:
        return False

    guess_raw = guess_raw.strip()
    if not guess_raw:
        return False

    guess_code = norm_code(guess_raw)
    guess_name = norm_text(guess_raw)
    guess_symbol = guess_raw

    single = len(currency_objects) == 1
    present_codes = {(c.get("code") or "").upper() for c in currency_objects}
    present_codes.discard("")

    # 1) ISO code check
    if guess_code and guess_code in present_codes:
        return True

    # 2) Bare-word defaults (e.g. "dollar" alone -> USD only)
    if guess_name in BARE_WORD_DEFAULT_CODE:
        return BARE_WORD_DEFAULT_CODE[guess_name] in present_codes

    # 3) Alias checks
    for c in currency_objects:
        aliases = currency_aliases(
            code=c.get("code") or "",
            name=c.get("name") or "",
            symbol=c.get("symbol"),
            single_currency_country=single,
        )

        for a in aliases:
            # If alias contains currency symbol characters, compare raw symbol
            if any(ch in _SYMBOL_CHARS for ch in a):
                if single and guess_symbol == a:
                    return True
            else:
                if guess_name and guess_name == a:
                    return True

    return False


def format_currency_answer(currency_objects: List[dict]) -> str:
    parts = []
    for c in currency_objects:
        code = (c.get("code") or "").upper()
        name = c.get("name") or ""
        if code and name:
            parts.append(f"{code} — {name}")
        elif name:
            parts.append(name)
        elif code:
            parts.append(code)
    return "; ".join(parts) if parts else ""