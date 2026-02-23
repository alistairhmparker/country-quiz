# app.py
import os
import time
import random
import json
import pathlib
import re

import requests
from flask import Flask, session, render_template, request, redirect, url_for
from flask_wtf import CSRFProtect
from utils import norm_text, norm_code, safe_first, parse_population_strict
from rules.currency import (
    currency_guess_is_correct,
    format_currency_answer,
)
from rules.language import language_guess_is_correct
from rules.competition import validate_player_name
from rules.competition import is_complete_country
from rules.language import language_guess_is_correct
from leaderboard import record_score, get_top_entries, format_played_at


app = Flask(__name__)


# --- About ---
ABOUT_GITHUB_URL = os.environ.get("ABOUT_GITHUB_URL", "https://github.com/alistairhmparker/country-quiz")
ABOUT_CREATOR = os.environ.get("ABOUT_CREATOR", "Alistair Parker")
ABOUT_CONTACT = os.environ.get("ABOUT_CONTACT", "your-email@example.com")
ABOUT_BLURB = os.environ.get(
    "ABOUT_BLURB",
    "Country Quiz is a Flask web app that generates geography quiz rounds from the RestCountries dataset."
)


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

LEADERBOARD_LIMIT = 20

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


def pick_unseen_complete_country(countries: list[dict], seen_names: set[str]) -> dict:
    """
    Pick a random country that has all four answers and hasn't been used in this competition run.
    If exhausted, reset seen (very unlikely in 5 rounds).
    """
    candidates = []
    for c in countries:
        name = ((c.get("name") or {}).get("common") or "")
        if not name or name in seen_names:
            continue
        fields = get_country_fields(c)
        if is_complete_country(fields):
            candidates.append(fields)

    if not candidates:
        # fallback: allow repeats if somehow exhausted
        for c in countries:
            fields = get_country_fields(c)
            if is_complete_country(fields):
                candidates.append(fields)

    return random.choice(candidates)


def clear_competition_session(keep_name: bool = False):
    keys = [
        "comp_name",
        "comp_round",
        "comp_score",
        "comp_seen",
        "comp_in_round",
        "comp_current",
    ]
    name = session.get("comp_name")
    for k in keys:
        session.pop(k, None)
    if keep_name and name:
        session["comp_name"] = name


# --- Routes ---

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/free")
def free():
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
        ok = language_guess_is_correct(raw, languages)
        if ok:
            score += 1
        add_result("Language", ok, raw, ", ".join(languages))

    # --- Currency ---
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


@app.route("/competition/start", methods=["GET", "POST"])
def competition_start():
    if request.method == "GET":
        return render_template("competition_start.html", error="", name_value="")

    name_raw = (request.form.get("name") or "").strip()
    ok, err = validate_player_name(name_raw)
    if not ok:
        return render_template("competition_start.html", error=err, name_value=name_raw)

    # Initialise competition session state
    session["comp_name"] = name_raw
    session["comp_round"] = 1
    session["comp_score"] = 0
    session["comp_seen"] = []

    return redirect(url_for("competition_play"))


@app.route("/competition/play", methods=["GET", "POST"])
def competition_play():
    # Must have started competition
    comp_name = session.get("comp_name")
    if not comp_name:
        return redirect(url_for("competition_start"))

    # Ensure state exists
    session.setdefault("comp_round", 1)
    session.setdefault("comp_score", 0)
    session.setdefault("comp_seen", [])
    session.setdefault("comp_in_round", False)
    session.setdefault("comp_current", None)

    countries = get_countries_cached()

    if request.method == "GET":
        # Keep same country during an in-progress round
        if session.get("comp_in_round") and session.get("comp_current"):
            current = session["comp_current"]
        else:
            seen = set(session.get("comp_seen") or [])
            current = pick_unseen_complete_country(countries, seen)
            session["comp_current"] = current
            session["comp_in_round"] = True

        return render_template(
            "index.html",  # reuse existing question page
            name=current.get("name"),
            capital=current.get("capital"),
            population=current.get("population"),
            languages=current.get("languages") or [],
            currencies=current.get("currencies") or [],
            # Hide free-mode stats in template (we’ll ignore these in display if template uses them)
            total_score=0,
            total_possible=0,
            rounds=0,
            countries_seen=0,
            comp_mode=True,
            comp_round=session["comp_round"],
            comp_name=comp_name,
        )

    # POST: score this round
    current = session.get("comp_current") or {}
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
    capital = current.get("capital")
    if capital:
        total += 1
        raw = (request.form.get("capital") or "").strip()
        ok = norm_text(raw) == norm_text(capital)
        if ok:
            score += 1
        add_result("Capital", ok, raw, capital)

    # Population (+/- 20%)
    population = current.get("population")
    if isinstance(population, int) and population > 0:
        total += 1
        raw_display = ((request.form.get("population_display") or "").strip())
        raw_hidden = ((request.form.get("population") or "").strip())
        raw = raw_display or raw_hidden

        guess_num = parse_population_strict(raw_hidden)
        ok = False if guess_num is None else (abs(guess_num - population) / population) <= 0.20

        if ok:
            score += 1
        add_result("Population", ok, raw, f"{population:,}")

    # Language (new rules)
    languages = current.get("languages") or []
    if languages:
        total += 1
        raw = (request.form.get("language") or "").strip()
        ok = language_guess_is_correct(raw, languages)
        if ok:
            score += 1
        add_result("Language", ok, raw, ", ".join(languages))

    # Currency
    currency_objects = current.get("currencies") or []
    if currency_objects:
        total += 1
        raw = (request.form.get("currency") or "").strip()
        ok = currency_guess_is_correct(raw, currency_objects)
        if ok:
            score += 1
        add_result("Currency", ok, raw, format_currency_answer(currency_objects))

    # Update competition totals
    session["comp_score"] = int(session.get("comp_score") or 0) + score

    # Mark this country as used in comp (after submit)
    name = current.get("name")
    if name:
        session["comp_seen"] = (session.get("comp_seen") or []) + [name]

    # End round
    session["comp_in_round"] = False
    session["comp_current"] = None

    comp_round = int(session.get("comp_round") or 1)
    comp_score = int(session.get("comp_score") or 0)

    # Advance round counter AFTER scoring
    # Round shown on results is the one just completed (comp_round).
    # Increment for next GET.
    if comp_round < 5:
        session["comp_round"] = comp_round + 1
    else:
        # keep at 5
        session["comp_round"] = 5

    return render_template(
        "competition_results.html",
        name=current.get("name"),
        score=score,
        total=total,
        results=results,
        comp_round=comp_round,
        comp_score=comp_score,
        comp_name=comp_name,
    )


@app.route("/competition/save", methods=["POST"])
def competition_save():
    comp_name = session.get("comp_name")
    if not comp_name:
        return redirect(url_for("competition_start"))

    comp_score = int(session.get("comp_score") or 0)

    record_score(comp_name, comp_score)

    # Clear comp state AFTER saving, but keep the name
    clear_competition_session(keep_name=True)

    # Store last score for the summary page
    session["last_comp_score"] = comp_score

    return redirect(url_for("competition_summary"))


@app.route("/competition/save", methods=["POST"])
def competition_save():
    comp_name = session.get("comp_name")
    if not comp_name:
        return redirect(url_for("competition_start"))

    comp_score = int(session.get("comp_score") or 0)

    record_score(comp_name, comp_score)

    # Clear comp state AFTER saving, but keep the name
    clear_competition_session(keep_name=True)

    # Store last score for the summary page
    session["last_comp_score"] = comp_score

    return redirect(url_for("competition_summary"))


@app.route("/stats")
def stats():
    leaderboard = get_top_entries(LEADERBOARD_LIMIT)
    leaderboard_view = [entry for entry in leaderboard]
    return render_template(
    "stats.html",
    leaderboard=leaderboard_view,
    about_github_url=ABOUT_GITHUB_URL,
    about_creator=ABOUT_CREATOR,
    about_contact=ABOUT_CONTACT,
    about_blurb=ABOUT_BLURB,
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
            ok = language_guess_is_correct(raw, languages)
            if ok:
                score += 1
            add_result("Language", ok, raw, ", ".join(languages))

        # Currency
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


try:
    # Create table if needed
    get_top_entries(1)
    app.logger.info("Leaderboard DB ready")
except Exception as e:
    app.logger.warning(f"Leaderboard init failed: {e}")


if __name__ == "__main__":

    app.run(debug=True)
