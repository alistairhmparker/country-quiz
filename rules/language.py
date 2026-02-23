# rules/language.py
from __future__ import annotations

import re
from typing import Iterable, Set

from utils import norm_text


# Curated synonyms you explicitly approve.
# Keys and values must be normalized (lowercase, accent-stripped).
LANGUAGE_SYNONYMS = {
    "persian": {"farsi"},
    "farsi": {"persian"},

    # Official language is Filipino, but most people say Tagalog.
    "filipino": {"tagalog"},
    "tagalog": {"filipino"},

    "burmese": {"myanmar"},
    "myanmar": {"burmese"},

    "greek": {"hellenic"},
    "hellenic": {"greek"},

    # Mandarin is the official language of China (Standard Chinese). People frequently answer Mandarin.
    "chinese": {"mandarin"},
    "mandarin": {"chinese"},

    "slovak": {"slovakian"},
    "slovakian": {"slovak"},

    "swahili": {"kiswahili"},
    "kiswahili": {"swahili"},

    "lao": {"laotian"},
    "laotian": {"lao"},

    # Technically ambiguous (Scottish Gaelic exists), but most quiz players mean Irish.
    "irish": {"gaelic"},
    "gaelic": {"irish"},

    # Norwegian / Norwegian Bokmål / Norwegian Nynorsk
    "norwegian bokmal": {"norwegian"},
    "norwegian nynorsk": {"norwegian"},
    "norwegian": {"norwegian bokmal", "norwegian nynorsk"},

    "malay": {"bahasa malaysia"},
    "bahasa malaysia": {"malay"},

    "indonesian": {"bahasa indonesia"},
    "bahasa indonesia": {"indonesian"},

    "hindi": {"hindustani"},
    "hindustani": {"hindi"},

    "romanian": {"moldovan"},
    "moldovan": {"romanian"},

    "khmer": {"cambodian"},
    "cambodian": {"khmer"},

    "sinhalese": {"sinhala"},
    "sinhala": {"sinhalese"},

    "haitian creole": {"haitian"},
    "haitian": {"haitian creole"},

    # Flemish is a common name for the Dutch spoken in Belgium. It's not technically a separate language, but many people answer "Flemish" and we want to accept that.
    "dutch": {"nederlands", "flemish"},
    "nederlands": {"dutch"},
    "flemish": {"dutch"},
}


_SPLIT_RE = re.compile(r"[(),;/]| and | or | aka | a\.k\.a\. ", re.IGNORECASE)


def _explode_label(label: str) -> Set[str]:
    """
    Turn one label like "Persian (Farsi)" into acceptable tokens:
      {"persian", "farsi"}
    Also handles commas, slashes, semicolons, and simple "and/or/aka".
    """
    out: Set[str] = set()
    if not label:
        return out

    # Split on common separators
    parts = _SPLIT_RE.split(label)

    for p in parts:
        n = norm_text(p)
        if n:
            out.add(n)

    # Also include the fully-normalized label (rarely needed but harmless)
    full = norm_text(label)
    if full:
        out.add(full)

    return out


def build_accepted_language_answers(languages: Iterable[str]) -> Set[str]:
    """
    Given a list of language labels from RestCountries, build the set of acceptable answers:
    - each label exploded into parts (e.g. Persian (Farsi) -> persian, farsi)
    - plus any curated synonyms for each accepted token
    """
    accepted: Set[str] = set()

    for label in languages:
        tokens = _explode_label(label)
        accepted |= tokens

    # Apply curated synonyms (explicit allowlist)
    expanded = set(accepted)
    for t in accepted:
        expanded |= LANGUAGE_SYNONYMS.get(t, set())

    return expanded


def language_guess_is_correct(guess_raw: str, languages: list[str]) -> bool:
    if not guess_raw:
        return False
    guess = norm_text(guess_raw)
    if not guess:
        return False

    accepted = build_accepted_language_answers(languages)
    return guess in accepted