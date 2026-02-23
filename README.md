# Country Quiz 🌍

A Flask-based geography quiz that generates rounds from the RestCountries dataset. Each round asks for the capital city, population (accepted within ±20%), official language (with sensible, curated synonyms), and currency (ISO codes + strict alias rules).

Play it live: https://country-quiz-p3yq.onrender.com

---

## Game Modes

### Free Practice Mode (Endless)

Endless random rounds with session-based stats: cumulative score / possible points, rounds played, and "countries explored" tracking (a country only counts once you submit, so refresh doesn't inflate stats).

Route: `GET /free`

### 5-Round Challenge (Leaderboard)

Enter a name, play 5 rounds, and post your final score to the leaderboard. Competition mode only selects "complete" countries (must have capital, population, language, and currency present). Name validation covers length/allowed chars, minimum letters, and a basic profanity filter. The leaderboard stores the **best score per player name** (only overwrites if improved).

Routes:
- `GET/POST /competition/start`
- `GET/POST /competition/play`
- `GET /competition/summary` — records score and shows leaderboard

### Landing / Navigation

`GET /` shows the primary navigation in this order: **5-Round Challenge**, **Free Practice Mode**, then **Challenge Stats**.

The project About information is also shown on the landing page in a de-emphasised footer.

---

## Answer Validation Rules

**Capital** — Exact match after normalisation (case + accent insensitive; punctuation collapsed).

**Population** — Parsed strictly as an integer (digits with optional commas/spaces). Correct if within ±20% of the official value.

**Language** — Uses a curated allowlist of sensible synonyms (e.g. *Filipino* ⇄ *Tagalog*, *Persian* ⇄ *Farsi*, *Chinese* ⇄ *Mandarin*). Also splits labels like "Persian (Farsi)" into acceptable tokens.

**Currency** — Deterministic hierarchy (no fuzzy matching): ISO code match (strongest), exact official currency name (normalised), core alias derived from official name (typically last word, e.g. "Azerbaijani manat" → "manat"), special-case defaults (bare "dollar" means USD only), curated aliases for specific codes (e.g. XOF/XAF "CFA franc", GBP "pound/sterling"), and currency symbol accepted only when the country has a single currency (to avoid ambiguity).

---

## Data Source, Caching, and Resilience

The primary source is RestCountries `v3.1/all` with a limited field set for speed. Data is held in an in-memory cache with a 6-hour TTL. A local fallback is periodically written to `data/countries_fallback.json` (best-effort, won't break requests). If the API is unreachable and there's no usable cache, the app attempts to load this fallback JSON.

---

## Leaderboard Storage

Two supported backends:

**Postgres** (recommended for deployment) — enabled when `DATABASE_URL` is set and `psycopg` is available.

**SQLite** (local dev fallback) — stored at `data/leaderboard.db` (or `${DATA_DIR}/leaderboard.db` if `DATA_DIR` is set).

---

## Project Structure
```text
country-quiz/
├── app.py
├── leaderboard.py
├── utils.py
├── rules/
│   ├── competition.py
│   ├── currency.py
│   └── language.py
├── templates/
│   ├── landing.html
│   ├── index.html
│   ├── results.html
│   ├── competition_start.html
│   ├── competition_results.html
│   ├── competition_summary.html
│   └── stats.html
├── tests/
│   ├── test_currency_rules.py
│   └── test_language_rules.py
├── .github/workflows/
│   └── ping.yml
├── requirements.txt
└── README.md
```

---

## Running Locally

**1. Clone**
```bash
git clone https://github.com/alistairhmparker/country-quiz.git
cd country-quiz
```

**2. Install dependencies**
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Dependencies include Flask, Flask-WTF, requests, gunicorn, pytest, tzdata, and psycopg (for Postgres).

**3. Run**
```bash
python app.py
```

Open the landing page at `http://127.0.0.1:5000/`.

---

## Environment Variables

**Required (production)**

`FLASK_SECRET_KEY` — long random secret for session signing. Generate one with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Optional**

| Variable | Description |
|---|---|
| `FLASK_HTTPS=1` | Marks session cookies as Secure when behind HTTPS |
| `DATABASE_URL` | Enables Postgres leaderboard when available |
| `DATA_DIR` | Overrides the local data directory used by the SQLite DB |
| `DEV_TOOLS_ENABLED=1` | Enables the dev test harness route |
| `ABOUT_GITHUB_URL` | About text shown on landing footer |
| `ABOUT_CREATOR` | About text shown on landing footer |
| `ABOUT_CONTACT` | About text shown on landing footer |
| `ABOUT_BLURB` | About text shown on landing footer |

---

## Dev Tools

When enabled, a dev-only page lets you pick a country and manually test scoring against the current rule logic.

Enable and run:
```bash
$env:DEV_TOOLS_ENABLED="1"
python app.py
```

Route: `GET/POST /dev/test`

---

## Testing
```bash
pytest
```

Unit tests focus on deterministic rule behaviour (currency + language).

**Health check** — `GET /health` returns `ok` (used for uptime / keep-awake pings).

---

## Deployment

**Gunicorn (example)**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 60
```

Works well on Render-style platforms.

**Keep-awake workflow (Render free tier)** — This repo includes a GitHub Actions workflow that pings `/health` on a schedule to reduce sleeping.

---

## License

MIT
