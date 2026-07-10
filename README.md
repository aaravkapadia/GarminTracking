# Garmin Daily Ingest

Pulls one day of [Garmin Connect](https://connect.garmin.com) stats, flattens and
cleans the raw payload, and upserts a single tidy row per day into a database. On top
of that it serves a read-only FastAPI + HTML dashboard and an LLM "online coach" that
reviews your recent trends.

- **Ingest** — daily job (launchd locally, or an in-process scheduler) that fetches
  stats, heart rate, and sleep, and writes one `daily_stats` row.
- **API + dashboard** — FastAPI endpoints and a single-page charts view at `/stats`.
- **Coach** — Claude Opus 4.8 turns the last ~14 days into readiness / workout /
  recovery advice.
- **Storage** — SQLite locally, Postgres in the cloud. Same code, driven by `DB_URL`.

---

## Quick start

```bash
# 1. Install (Python 3.9.6)
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Configure — create a .env in the project root (see below)

# 3. Backfill and serve
.venv/bin/python -m src.ingest.scheduler --once          # ingest today
.venv/bin/uvicorn src.api.routes:app --reload            # open http://127.0.0.1:8000/stats
```

### `.env`

```ini
GARMIN_EMAIL=you@example.com
GARMIN_PASSWORD=your-password
DB_URL=sqlite:///garmin.db
ANTHROPIC_API_KEY=sk-ant-...            # required for the coach only

# Optional: a saved Garmin session token (see "Auth" below). If set, it is
# used instead of email/password — handy for headless/cloud deploys.
# GARMIN_TOKEN_BASE64=...
```

`.env` is gitignored. `load_dotenv()` runs at import, so these reach `os.environ`.

---

## Layout

| Path | What it does |
| --- | --- |
| `src/ingest/client.py` | `get_client()` (login via token or email/password) and `fetch_daily_stats()` (raw stats / heart-rate / sleep payload). |
| `src/ingest/scheduler.py` | The ingest job: `format_daily_stats()` cleans one row (44 columns), `ingest_day()` upserts via `session.merge()`, plus `--once` / `--date` / `--start`/`--end` CLI modes and the in-process scheduler. |
| `src/db/model.py` | SQLAlchemy 2.0 `DailyStats` model. **`calendar_date` is the primary key**, so re-ingesting a day upserts instead of duplicating. |
| `src/db/db.py` | `engine`, `SessionLocal`, `init_db()`. Builds the engine from `DB_URL` and normalizes Railway-style `postgres://` URLs to `postgresql+pg8000://`. |
| `src/api/routes.py` | Read-only FastAPI: `/health`, `/days`, `/days/latest`, `/days/{date}`, `/coach`, and the `/stats` HTML dashboard. Starts a background daily-ingest scheduler on app startup. |
| `src/coach/coach.py` | The LLM coach. `get_coaching(days=14, extra_note=…)` builds a one-line-per-day digest and asks Claude Opus 4.8 for markdown advice. Cached in-process until a new day is ingested. |
| `scripts/dump_garmin_token.py` | Prints a `GARMIN_TOKEN_BASE64` for a saved login session. |
| `railway.json` | Railway/NIXPACKS deploy config (uvicorn start command, `/health` healthcheck). |

---

## Running

```bash
# One-off ingest (hits the real Garmin account)
.venv/bin/python -m src.ingest.scheduler --once

# Backfill a single past day
.venv/bin/python -m src.ingest.scheduler --date 2026-06-01

# Backfill an inclusive range (one login for the whole range)
.venv/bin/python -m src.ingest.scheduler --start 2026-06-01 --end 2026-06-30

# In-process scheduler (foreground; alternative to launchd)
.venv/bin/python -m src.ingest.scheduler

# Serve the API + dashboard (coach panel at the top of /stats)
.venv/bin/uvicorn src.api.routes:app --reload

# Ask the coach from the CLI
.venv/bin/python -m src.coach.coach --days 14 --note "race Saturday"

# Inspect the DB
.venv/bin/python -c "from src.db.db import SessionLocal; from src.db.model import DailyStats; \
print([r.calendar_date for r in SessionLocal().query(DailyStats)])"
```

---

## API

| Endpoint | Description |
| --- | --- |
| `GET /health` | Liveness check (`{"status": "ok"}`). |
| `GET /stats` | Single-page HTML dashboard (charts + coach). |
| `GET /days?limit=N` | All ingested days, newest first. |
| `GET /days/latest` | Most recently ingested day. |
| `GET /days/{date}` | Full stats for one `YYYY-MM-DD` (404 if not ingested). |
| `GET /coach?days=14&note=…&refresh=false` | LLM coaching over recent history. `refresh=true` bypasses the cache. |

Interactive docs at `/docs`.

---

## Auth

Two ways to log in, checked in this order by `get_client()`:

1. **`GARMIN_TOKEN_BASE64`** — a saved session token. Preferred for headless/cloud
   runs since it survives IP changes and avoids repeated MFA prompts. Generate one
   locally with:
   ```bash
   .venv/bin/python -m scripts.dump_garmin_token
   ```
   Copy the printed value into `.env` (or your host's env vars).
2. **`GARMIN_EMAIL` / `GARMIN_PASSWORD`** — a fresh login. A live run may trigger
   MFA / login-token prompts on first use.

---

## Scheduling (macOS launchd)

The daily job runs via a LaunchAgent — it survives reboots and catches up a missed run
shortly after wake if the Mac was asleep at 23:59 (a full shutdown at that time means
no run).

- Plist: `~/Library/LaunchAgents/com.aaravkapadia.garmin.dailyingest.plist`
- Runs `.venv/bin/python -m src.ingest.scheduler --once` with `WorkingDirectory` set to
  the project root, at Hour 23 / Minute 59. `RunAtLoad=false`. Logs to
  `logs/ingest.{out,err}.log`.

```bash
launchctl print gui/$(id -u)/com.aaravkapadia.garmin.dailyingest          # status
launchctl kickstart -k gui/$(id -u)/com.aaravkapadia.garmin.dailyingest   # run now
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.aaravkapadia.garmin.dailyingest.plist  # load
launchctl bootout   gui/$(id -u) ~/Library/LaunchAgents/com.aaravkapadia.garmin.dailyingest.plist  # unload
```

When the API is running, `src/api/routes.py` also starts an in-process
`BackgroundScheduler` at 23:59 — the deployed (Railway) equivalent of the LaunchAgent.

---

## Deployment (Railway)

`railway.json` builds with NIXPACKS and starts:

```
uvicorn src.api.routes:app --host 0.0.0.0 --port $PORT
```

with a `/health` healthcheck. Set these variables on the service:

- `DB_URL` — Railway's Postgres URL (`postgres://…` is normalized automatically to the
  `pg8000` driver, and `sslmode` is stripped from the query string).
- `GARMIN_TOKEN_BASE64` — saved session token (avoids MFA on the host).
- `ANTHROPIC_API_KEY` — for the coach.

---

## Gotchas

- **The drop step in `format_daily_stats` is effectively a no-op.** Drop substrings are
  camelCase but compared against `col.lower()`, so they never match — the `keep` list is
  what actually selects the 44 columns. Do **not** lowercase the drop substrings; that
  would wrongly remove `sleep_avgSleepStress`.
- **`DB_URL` is required** and, for SQLite, is a relative path — it resolves against the
  current working directory. Run from the project root (launchd sets `WorkingDirectory`).
- **Coach caching** — advice is cached in-process keyed by `(days, note, latest ingested
  day)`, so repeat calls reuse it until a new day lands. Use `?refresh=true` (API) or
  `force=True` (code) to regenerate.

---

## Requirements

Python 3.9.6 (pinned in `.python-version`). Key dependencies (`requirements.txt`):
`fastapi`, `uvicorn[standard]`, `sqlalchemy`, `pandas`, `garminconnect`, `apscheduler`,
`python-dotenv`, `anthropic`, `pg8000`.
