# Country Quiz
A web-based geography quiz built with Flask. The application presents a random country each round and asks the user to identify its capital, population, official language, and currency. It includes structured answer validation, session-based scoring, and a responsive interface suitable for desktop and mobile use.

## Overview
The quiz is designed to balance playability with accuracy. Answers are normalised for case and accents, population guesses are evaluated within a tolerance band, and currency matching supports ISO codes alongside full names.
The application is lightweight, stateless on the server side (beyond session cookies), and suitable for simple public deployment.

## Features
- Random country selection each round
- Session-based cumulative scoring
- "Countries explored" tracking
- Population answers accepted within ±20%
- Currency validation supporting:
  - ISO codes (e.g. USD, GBP)
  - Exact currency names
  - Limited curated aliases
- Case and accent insensitive text matching
- CSRF protection via Flask-WTF
- API response caching for performance
- Mobile-friendly interface

## Technology Stack
- Python / Flask
- Flask-WTF (CSRF protection)
- Gunicorn (production server)
- RestCountries API
- HTML, CSS, vanilla JavaScript

## Running Locally
1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/country-quiz.git
cd country-quiz
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Start the development server
```bash
python app.py
```

Then visit:
```
http://127.0.0.1:5000
```

## Deployment (Render)
The app is configured for straightforward deployment on Render or similar platforms. Render Free sleeps after inactivity; see .github/workflows/ping.yml for keep-awake pings.

**Build command**
```bash
pip install -r requirements.txt
```

**Start command**
```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 60
```

**Required environment variable**
Set in the hosting platform:
```
FLASK_SECRET_KEY=<long random string>
```
Generate locally with:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Project Structure
```
country-quiz/
├── app.py
├── requirements.txt
└── templates/
    ├── index.html
    └── results.html
```

## Answer Rules
- Capital and language must match after normalisation (case and accents ignored).
- Population is marked correct if within ±20% of the true value.
- Currency accepts ISO codes, exact currency names, and limited curated aliases.
- "Countries explored" increments after a submitted round.

## Data Source
Country data is provided by the RestCountries API: https://restcountries.com

## License
MIT License
