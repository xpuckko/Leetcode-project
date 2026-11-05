# Online Judge API

A FastAPI backend for an online coding judge. Users register, log in, and browse programming problems. Admins manage problems and the supported languages. Code execution through Judge0 is planned.

> Work in progress: data is stored in memory and resets on every restart. A SQL database is planned.

## Features

- User registration and login with JWT authentication
- UUID identifiers for users and problems
- Roles (`user`, `admin`) with access checks
- Problems with difficulty, limits and visibility (`is_visible`); hidden problems are only visible to admins
- Language catalog, managed by admins (in progress)

## Requirements

- Python 3.13
- Packages listed in `requirements.txt`

## Setup

```bash
git clone https://github.com/xpuckko/Leetcode-project.git
cd Leetcode-project
python -m venv .venv
.venv\Scripts\activate        # Windows (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Create a `.env` file in the project root (never commit it):

```
SECRET_KEY=<long random string>
```

Generate a key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Run

```bash
uvicorn main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

## Test

```bash
pytest -v
```

## Endpoints (summary)

| Resource | Access |
|----------|--------|
| `POST /users/`, `POST /login` | public |
| `GET /users/me`, `GET/PATCH/DELETE /users/{id}` | self or admin |
| `GET /users/` | admin |
| `GET /problems/`, `GET /problems/{id}` | logged-in users (hidden problems: admin only) |
| `POST/PUT/DELETE /problems/...` | admin |
| `POST /languages/` | admin |

## Known limitations / TODO

- In-memory storage (switch to SQL)
- No seeded admin account yet, so admin endpoints are only exercised in tests
- No rate limiting on `/login`
- Judge0 integration and submissions not implemented