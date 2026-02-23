# app.py
import os
import time
import random
import json
import pathlib

import requests
from flask import Flask, session, render_template, request, redirect, url_for
from flask_wtf import CSRFProtect
from utils import norm_text, norm_code, safe_first, parse_population_strict
from rules.currency import (
    currency_guess_is_correct,
    format_currency_answer,
)

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

DEV_TOOLS_ENABLED = os.environ.get("DEV_TOOLS_ENABLED") == "1"

RESTCOUNTRIES_URL = (
    "https://restcountries.com/v3.1/all"
    "?fields=name,capital,population,languages,currencies,flag,subregion,area,borders"
)

# --- Data / fallback ---
DATA_DIR = pathlib.Path(__file__).resolve().parent / "data"
LOCAL_COUNTRIES_FALLBACK = DATA_DIR / "countries_fallback.json"

FALLBACK_REFRESH_DAYS = 7
FALLBACK_REFRESH_SECONDS = FALLBACK_REFRESH_DAYS * 24 * 60 * 60


def load_fallback_countries():
    if not LOCAL_COUNTRIES_FALLBACK.exists():
        return None
    with LOCAL_COUNTRIES_FALLBACK.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_fallback_countries(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # atomic-ish write: write temp then replace
    tmp_path = LOCAL_COUNTRIES_FALLBACK.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp_path.replace(LOCAL_COUNTRIES_FALLBACK)


def fallback_is_stale(now: float) -> bool:
    try:
        mtime = LOCAL_COUNTRIES_FALLBACK.stat().st_mtime
        return (now - mtime) > FALLBACK_REFRESH_SECONDS
    except FileNotFoundError:
        return True


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


        # Periodically refresh local fallback file (best effort; never breaks the request)
        try:
            if fallback_is_stale(now):
                save_fallback_countries(data)
                app.logger.info("Refreshed local fallback countries JSON")
        except Exception as e:
            app.logger.warning(f"Failed to refresh fallback JSON: {e}")
        return data
    
    except Exception as e:
        # If refresh fails but we have old data, serve stale cache
        if _COUNTRY_CACHE["data"] is not None:
            app.logger.warning(f"RestCountries refresh failed; serving stale cache. Error: {e}")
            return _COUNTRY_CACHE["data"]

        # No cached data at all: try local fallback
        try:
            data = load_fallback_countries()
            if data:
                _COUNTRY_CACHE["data"] = data
                _COUNTRY_CACHE["fetched_at"] = now
                
                app.logger.warning("Loaded countries from local fallback JSON")
                return data
        except Exception as e2:
            app.logger.warning(f"Failed to load fallback JSON: {e2}")

        raise


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


@app.route("/dev/test", methods=["GET", "POST"])
def dev_test():
    if not DEV_TOOLS_ENABLED:
        return "Dev tools disabled", 404

    countries = get_countries_cached()

    # Build dropdown list (common names)
    country_names = sorted(
        [(c.get("name") or {}).get("common") for c in countries if (c.get("name") or {}).get("common")]
    )

    selected_name = (request.values.get("country") or "").strip()
    selected_country = None
    if selected_name:
        for c in countries:
            if ((c.get("name") or {}).get("common") == selected_name):
                selected_country = c
                break

    results = None
    fields = None

    # If a country is selected (GET or POST), compute fields so the template can show "Correct answers"
    if selected_country:
        fields = get_country_fields(selected_country)

    if request.method == "POST" and selected_country:
        fields = get_country_fields(selected_country)

        # Use the same scoring logic as /submit (but without sessions)
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

        # Capital
        capital = fields.get("capital")
        if capital:
            total += 1
            raw = (request.form.get("capital") or "").strip()
            ok = norm_text(raw) == norm_text(capital)
            if ok:
                score += 1
            add_result("Capital", ok, raw, capital)

        # Population (+/- 20%)
        population = fields.get("population")
        if isinstance(population, int) and population > 0:
            total += 1
            raw_hidden = (request.form.get("population") or "").strip()
            guess_num = parse_population_strict(raw_hidden)
            ok = False if guess_num is None else (abs(guess_num - population) / population) <= 0.20
            if ok:
                score += 1
            your_display = raw_hidden
            if guess_num is not None:
                your_display = f"{guess_num:,}"
            add_result("Population", ok, your_display, f"{population:,}")

        # Language (accept any listed)
        languages = fields.get("languages") or []
        if languages:
            total += 1
            raw = (request.form.get("language") or "").strip()
            ok = norm_text(raw) in [norm_text(l) for l in languages]
            if ok:
                score += 1
            add_result("Language", ok, raw, ", ".join(languages))

        # Currency (your Rule 4)
        currency_objects = fields.get("currencies") or []
        if currency_objects:
            total += 1
            raw = (request.form.get("currency") or "").strip()
            ok = currency_guess_is_correct(raw, currency_objects)
            if ok:
                score += 1
            add_result("Currency", ok, raw, format_currency_answer(currency_objects))

        # Add overall score at top
        results.insert(
            0,
            {
                "field": "Total",
                "ok": (score == total),
                "your_answer": f"{score}/{total}",
                "correct_answer": "—",
            },
        )

    return render_template(
        "dev_test.html",
        country_names=country_names,
        selected_name=selected_name,
        fields=fields,
        results=results,
        format_currency_answer=format_currency_answer,
    )


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
