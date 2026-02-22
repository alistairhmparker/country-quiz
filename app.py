# app.py
import os
import time
import random
import unicodedata
import re

import requests
from flask import Flask, session, render_template, request, redirect, url_for
from flask_wtf import CSRFProtect

app = Flask(__name__)

# --- Security / config ---
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-only-change-me")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(
        os.environ.get("FLASK_HTTPS")
    ),  # set FLASK_HTTPS=1 behind HTTPS
)

csrf = CSRFProtect(app)

RESTCOUNTRIES_URL = (
    "https://restcountries.com/v3.1/all"
    "?fields=name,capital,population,languages,currencies,flag,subregion,area,borders"
)

# --- Cache ---
_COUNTRY_CACHE = {"data": None, "fetched_at": 0.0}
CACHE_TTL_SECONDS = 60 * 60 * 6  # 6 hours


def fetch_countries():
    r = requests.get(RESTCOUNTRIES_URL, timeout=12)
    r.raise_for_status()
    return r.json()


def get_countries_cached():
    now = time.time()

    # If we have data and it's still fresh, just return it
    if _COUNTRY_CACHE["data"] is not None and (now - _COUNTRY_CACHE["fetched_at"]) <= CACHE_TTL_SECONDS:
        return _COUNTRY_CACHE["data"]

    # Otherwise try to refresh
    try:
        data = fetch_countries()
        _COUNTRY_CACHE["data"] = data
        _COUNTRY_CACHE["fetched_at"] = now
        return data
    except Exception as e:
        # If refresh fails but we have old data, serve stale cache
        if _COUNTRY_CACHE["data"] is not None:
            app.logger.warning(f"RestCountries refresh failed; serving stale cache. Error: {e}")
            return _COUNTRY_CACHE["data"]

        # No cached data at all: re-raise (site can't function without any country list)
        raise


# --- Normalisation helpers ---
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


def safe_first(lst):
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


# --- Currency matching (Rule 4 polished) ---
GENERIC_CURRENCY_TYPES = {
    "dollar",
    "peso",
    "franc",
    "riyal",
    "rial",
    "dinar",
    "dirham",
    "rupee",
    "ruble",
    "rouble",
    "krona",
    "krone",
    "kronor",
    "koruna",
    "crown",
    "yen",
    "yuan",
    "renminbi",
    "won",
    "rand",
    "real",
    "zloty",
    "forint",
    "leu",
    "lei",
    "lira",
    "shekel",
    "shilling",
    "baht",
}

# A small curated extras map (kept tight; no fuzz)
EXTRA_CURRENCY_ALIASES_BY_CODE = {
    "USD": {"us dollar", "u s dollar"},
    "GBP": {"pound sterling", "sterling", "pound"},
    "EUR": {"euro"},
    "JPY": {"yen"},
    "CNY": {"yuan", "renminbi", "rmb"},
    "KRW": {"won"},
    "INR": {"rupee"},
    "RUB": {"ruble", "rouble"},
    # CFA francs
    "XAF": {"cfa franc", "central african cfa franc", "cfa"},
    "XOF": {"cfa franc", "west african cfa franc", "cfa"},
}


def currency_aliases(
    code: str, name: str, symbol: str | None, single_currency_country: bool
):
    """
    Build acceptable aliases for one currency:
    - ISO code always accepted
    - exact currency name accepted (normalized)
    - curated aliases for certain codes (e.g., USD, GBP)
    - generic currency-type words accepted ONLY if single-currency-country AND type appears in name
    - symbol accepted ONLY if single-currency-country (to avoid ambiguity)
    """
    code_u = (code or "").upper()
    name_n = norm_text(name)
    aliases = set()

    if code_u:
        aliases.add(code_u)  # ISO code (raw)
        aliases.add(norm_text(code_u))  # mostly redundant, but safe

    if name_n:
        aliases.add(name_n)

    # curated extras by ISO code
    for a in EXTRA_CURRENCY_ALIASES_BY_CODE.get(code_u, set()):
        aliases.add(norm_text(a))

    # generic-type acceptance only when unambiguous (single currency country)
    if single_currency_country and name_n:
        for t in GENERIC_CURRENCY_TYPES:
            if t in name_n.split():
                aliases.add(t)

    # symbol acceptance only when unambiguous (single currency country)
    if single_currency_country and symbol:
        # store raw symbol as-is (we'll compare raw trimmed)
        aliases.add(symbol.strip())

    return aliases


def currency_guess_is_correct(guess_raw: str, currency_objects: list[dict]) -> bool:
    """
    Determine if the guess matches any currency (Rule 4 polished):
    - ISO code match (letters-only) is strongest
    - exact name match (normalized)
    - curated aliases
    - optional symbol match only if unambiguous
    - optional generic type word only if unambiguous
    """
    if not guess_raw:
        return False

    guess_raw = guess_raw.strip()
    if not guess_raw:
        return False

    guess_code = norm_code(guess_raw)  # e.g. "usd", "USD", "U.S.D." -> "USD"
    guess_name = norm_text(guess_raw)  # name-like normalization
    guess_symbol = guess_raw  # keep raw for symbol exact match

    single = len(currency_objects) == 1

    # First: ISO code check
    if guess_code:
        for c in currency_objects:
            if guess_code == (c.get("code") or "").upper():
                return True

    # Then: name/alias checks
    for c in currency_objects:
        aliases = currency_aliases(
            code=c.get("code") or "",
            name=c.get("name") or "",
            symbol=c.get("symbol"),
            single_currency_country=single,
        )

        # If alias is a raw symbol, compare to raw; otherwise compare normalized text
        for a in aliases:
            if len(a) <= 4 and any(
                ch in a for ch in "€£$¥₩₽₹₺₫₦₱₲₴₡₸₺₵₭₮₪₨"
            ):  # crude "symbol-ish" check
                if single and guess_symbol == a:
                    return True
            else:
                if guess_name and guess_name == a:
                    return True

    return False


def format_currency_answer(currency_objects: list[dict]) -> str:
    """
    Pretty answer like:
    'USD — United States dollar; ...'
    """
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


def get_country_fields(country: dict):
    name = (country.get("name") or {}).get("common")
    capital = safe_first(country.get("capital") or [])
    population = country.get("population", None)
    languages = list((country.get("languages") or {}).values())

    # currencies dict is like {"USD": {"name": "...", "symbol": "$"}, ...}
    cur_dict = country.get("currencies") or {}
    currency_objects = []
    for code, info in cur_dict.items():
        info = info or {}
        currency_objects.append(
            {"code": code, "name": info.get("name") or "", "symbol": info.get("symbol")}
        )

    return {
        "name": name,
        "capital": capital,
        "population": population if isinstance(population, int) else None,
        "languages": languages,
        "currencies": currency_objects,  # list of dicts {code,name,symbol}
    }


# --- Routes ---
@app.route("/")
def index():
    countries = get_countries_cached()

    session.setdefault("seen", [])  # explored = submitted
    session.setdefault("total_score", 0)
    session.setdefault("total_possible", 0)
    session.setdefault("rounds", 0)
    session.setdefault("in_round", False)

    # Keep the same country during an in-progress round
    if session.get("in_round") and session.get("current"):
        current = session["current"]
    else:
        seen = set(session["seen"])
        unseen = [
            c for c in countries if ((c.get("name") or {}).get("common") not in seen)
        ]
        if not unseen:
            session["seen"] = []
            unseen = countries

        picked = random.choice(unseen)
        current = get_country_fields(picked)
        session["current"] = current
        session["in_round"] = True

    # For templates, currencies presence is what matters; the input field stays the same.
    return render_template(
        "index.html",
        name=current.get("name"),
        capital=current.get("capital"),
        population=current.get("population"),
        languages=current.get("languages") or [],
        currencies=current.get("currencies") or [],
        total_score=session["total_score"],
        total_possible=session["total_possible"],
        rounds=session["rounds"],
        countries_seen=len(session["seen"]),
    )


@app.route("/submit", methods=["POST"])
def submit():
    current = session.get("current") or {}

    score = 0
    total = 0
    results = []

    def add_result(field: str, ok: bool, your_answer: str, correct_answer: str):
        results.append(
            {
                "field": field,
                "ok": ok,
                "your_answer": your_answer if your_answer else "—",
                "correct_answer": correct_answer if correct_answer else "—",
            }
        )

    # --- Capital ---
    capital = current.get("capital")
    if capital:
        total += 1
        raw = request.form.get("capital", "").strip()
        ok = norm_text(raw) == norm_text(capital)
        if ok:
            score += 1
        add_result("Capital", ok, raw, capital)

    # --- Population (+/- 20%) ---
    population = current.get("population")
    if isinstance(population, int) and population > 0:
        total += 1
        raw_display = (
            request.form.get("population_display", "") or ""
        ).strip()  # if you ever add it
        raw_hidden = (request.form.get("population", "") or "").strip()
        raw = raw_display or raw_hidden  # show the pretty one if present

        guess_num = parse_population_strict(raw_hidden)
        if guess_num is None:
            ok = False
        else:
            ok = (abs(guess_num - population) / population) <= 0.20

        if ok:
            score += 1
        add_result("Population", ok, raw, f"{population:,}")

    # --- Language ---
    languages = current.get("languages") or []
    if languages:
        total += 1
        raw = request.form.get("language", "").strip()
        ok = norm_text(raw) in [norm_text(l) for l in languages]
        if ok:
            score += 1
        add_result("Language", ok, raw, ", ".join(languages))

    # --- Currency (Rule 4 polished + ISO) ---
    currency_objects = current.get("currencies") or []
    if currency_objects:
        total += 1
        raw = request.form.get("currency", "").strip()
        ok = currency_guess_is_correct(raw, currency_objects)
        if ok:
            score += 1
        add_result("Currency", ok, raw, format_currency_answer(currency_objects))

    # Update cumulative stats
    session["total_score"] += score
    session["total_possible"] += total
    session["rounds"] += 1

    # Mark explored only after submit (prevents refresh inflation)
    name = current.get("name")
    if name and name not in session["seen"]:
        session["seen"] = session["seen"] + [name]

    session["in_round"] = False

    return render_template(
        "results.html",
        name=current.get("name"),
        score=score,
        total=total,
        results=results,
        total_score=session["total_score"],
        total_possible=session["total_possible"],
        rounds=session["rounds"],
        countries_seen=len(session["seen"]),
    )


@app.route("/reset")
def reset():
    session.clear()
    return redirect(url_for("index"))


@app.get("/health")
def health():
    return "ok", 200


def warm_country_cache():
    try:
        get_countries_cached()
        app.logger.info("Country cache warmed")
    except Exception as e:
        app.logger.warning(f"Cache warm failed: {e}")


# Warm cache when worker starts
warm_country_cache()

if __name__ == "__main__":

    app.run(debug=True)
