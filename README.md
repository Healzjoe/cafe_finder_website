# Cafe & Wifi

A website for finding work-friendly cafes. Visitors can search by location, see Wi-Fi, power sockets, toilets, call policy, seats and coffee prices, and get a random cafe suggestion. An admin logs in to add, edit and delete cafes.

## Features

- Browse all cafes, with cards showing amenities
- Search cafes by location (case-insensitive)
- Random cafe suggestion
- Admin login protected by a hashed password, rate-limited to 5 attempts per minute
- Add, edit and delete cafes (admin only)
- Duplicate cafe names are blocked, ignoring capital letters
- JSON API, protected by an API key, for search and listing

## Tech stack

- Python, Flask
- Flask-SQLAlchemy (SQLite locally, PostgreSQL in production)
- Flask-WTF (forms and CSRF protection)
- Flask-Limiter (login rate limiting)
- Gunicorn (production server)
- HTML, CSS and a small amount of JavaScript

## Setup

1. Clone the repository and create a virtual environment:

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in the values:

   ```
   SECRET_KEY=a-long-random-string
   CAFE_API_KEY=a-long-random-string
   ADMIN_PASSWORD_HASH='scrypt:...'
   ```

3. Create the admin password hash, using a password of your choice:

   ```
   python make_hash.py
   ```

   Copy the printed line into `ADMIN_PASSWORD_HASH`.

4. Run the app:

   ```
   python main.py
   ```

   Open http://127.0.0.1:5000

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | signs sessions and CSRF tokens (required) |
| `CAFE_API_KEY` | key for the JSON API, sent in the `X-API-KEY` header |
| `ADMIN_PASSWORD_HASH` | hash of the admin password. Never store the plain password. |
| `DB_URI` | database address. Defaults to `sqlite:///cafes.db` |
| `COOKIE_SECURE` | set to `1` on HTTPS hosting |
| `RATE_LIMIT_STORAGE` | optional Redis URL for login limits that survive restarts |
| `FLASK_DEBUG` | set to `1` only on your own computer |

## API

All API routes require the header `X-API-KEY: your-key`.

| Route | Method | Purpose |
|---|---|---|
| `/all` | GET | list all cafes |
| `/search?loc=...` | GET | cafes in a location |
| `/random` | GET | one random cafe |

## Security

- Passwords are stored as salted hashes, never in plain text
- Session cookies are HttpOnly and SameSite
- Forms use CSRF tokens
- Edit, delete and add require admin login
- Security headers are sent with every response

## Deployment

Designed for Render with a PostgreSQL database. Set the environment variables in the Render dashboard, not in any file in the repository. Start command: `gunicorn -w 1 main:app`

## Author

Joseph Eneji