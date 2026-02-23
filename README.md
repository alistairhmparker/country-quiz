# Country Quiz

A web-based geography quiz built with Flask. Each round presents a random country and challenges the user to identify its capital, population, official language, and currency.

The application emphasises structured validation, deterministic rules, and clean architecture, while remaining lightweight and easy to deploy.

## Overview

Country Quiz balances playability with accuracy:

- Text answers are normalised (case + accent insensitive).
- Population guesses are accepted within a ±20% tolerance.
- Currency matching supports ISO codes, descriptor-stripped names (e.g. `manat`), and controlled alias rules.
- Session-based scoring tracks cumulative performance.

The application is server-light (session cookies only) and suitable for simple public deployment.

## Features

- Random country selection per round
- Session-based cumulative scoring
- "Countries explored" tracking
- Population accepted within ±20%
- Structured currency validation supporting:
  - ISO codes (`USD`, `GBP`, etc.)
  - Official names
  - Descriptor-stripped names (e.g. `manat`, `lek`)
  - Controlled default behaviour (`dollar` ⇒ USD)
  - Curated aliases (e.g. `cfa franc`)
- Case and accent insensitive text matching
- CSRF protection (Flask-WTF)
- API response caching
- Local fallback dataset for resilience
- Mobile-friendly UI
- Dev-only test harness for rule verification

## Technology Stack

- Python 3
- Flask
- Flask-WTF (CSRF)
- Gunicorn (production server)
- RestCountries API
- HTML / CSS / vanilla JavaScript
- Pytest (unit testing)

## Project Structure

```
country-quiz/
├── app.py
├── rules/
│   ├── __init__.py
│   └── currency.py
├── utils.py
├── templates/
│   ├── index.html
│   ├── results.html
│   └── dev_test.html
├── tests/
│   └── test_currency_rules.py
├── data/                # local fallback (ignored by git)
├── .github/
├── requirements.txt
└── README.md
```

## Answer Rules

### Capital & Language

Must match after normalisation (case + accent insensitive).

### Population

Correct if within ±20% of the official value.

### Currency

Validation follows a structured hierarchy:

1. ISO code match (strongest)
2. Exact official name
3. Descriptor-stripped core name
   - e.g. `"Azerbaijani manat"` ⇒ `manat`
4. Controlled defaults
   - `"dollar"` alone maps to USD only
5. Curated aliases
   - e.g. `cfa franc`

This keeps the system predictable while avoiding over-permissive fuzzy matching.

## Running Locally

**1. Clone the repository**

```bash
git clone https://github.com/alistairhmparker/country-quiz.git
cd country-quiz
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Run the development server**

```bash
python app.py
```

Visit: `http://127.0.0.1:5000`

## Dev Tools

To enable development-only routes:

**PowerShell**

```powershell
$env:DEV_TOOLS_ENABLED="1"
python app.py
```

Available routes:

- `/dev/test` — rule validation harness
- `/dev/refresh-fallback` — refresh local country dataset

## Testing

Run unit tests:

```bash
pytest
```

Tests currently cover currency rule behaviour (e.g. `"dollar"` default logic, CFA handling, descriptor stripping).

## Deployment (Render)

Designed for straightforward deployment on Render or similar platforms.

> Render Free sleeps after inactivity. See `.github/workflows/ping.yml` for keep-awake pings.

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 60
```

**Required Environment Variable**

```
FLASK_SECRET_KEY=<long random string>
```

Generate locally:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Data Source

Country data provided by [RestCountries](https://restcountries.com).

A local fallback dataset is stored in `data/` for resilience if the API is unavailable.

## License

MIT License