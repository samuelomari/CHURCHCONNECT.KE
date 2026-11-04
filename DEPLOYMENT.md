# Deploying ChurchConnect Kenya for Free

ChurchConnect Kenya is a Python/Flask app with a SQLite database and a
single-page frontend served by Flask. The easiest **free** options are:

## Option 1 — Render (free web service, recommended)

1. Push this repo to GitHub (already at `samuelomari/CHURCHCONNECT.KE`).
2. Create a free account at https://render.com and click **New → Web Service**.
3. Connect your GitHub repo. Render auto-detects `requirements.txt` and
   `Procfile`.
4. Set these environment variables in the Render dashboard:
   - `SECRET_KEY` = a long random string (32+ chars)
   - `JWT_SECRET` = a different long random string (32+ chars)
   - `DATABASE_FILE` = `/opt/render/project/src/churchconnect.db` (or attach a
     persistent disk)
   - `FORCE_HTTPS` = `true`
   - `FLASK_DEBUG` = `false`
5. Build command: `pip install -r requirements.txt`
   Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`
6. Click **Create Web Service**. Render builds and deploys. Free tier sleeps
   after 15 min of inactivity (first request wakes it in ~30s).

> ⚠️ Free Render web services have an **ephemeral filesystem**. SQLite data is
> reset on every redeploy/restart. For a church in production, attach a
> Render **Persistent Disk** (paid) OR use a free external database (see below).

## Option 2 — PythonAnywhere (free, persistent SQLite)

1. Create a free account at https://www.pythonanywhere.com.
2. Upload/clone the repo into your home directory.
3. In a Bash console:
   ```bash
   cd ~/CHURCHCONNECT.KE
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   python3 seed.py   # one-time
   ```
4. Web tab → **Add a new web app** → Manual configuration → Python 3.11.
5. Set source code path to `/home/<username>/CHURCHCONNECT.KE`.
6. WSGI file: point to `app:app`:
   ```python
   import sys
   path = '/home/<username>/CHURCHCONNECT.KE'
   if path not in sys.path: sys.path.insert(0, path)
   from app import app as application
   ```
7. Set environment variables (SECRET_KEY, JWT_SECRET) in the WSGI file or
   via the PythonAnywhere dashboard.
8. Reload. Your app is live at `https://<username>.pythonanywhere.com`.

SQLite file persists on PythonAnywhere's filesystem (free tier).

## Option 3 — Fly.io (free allowance)

```bash
fly launch --no-deploy
fly secrets set SECRET_KEY=... JWT_SECRET=...
fly deploy
```
Use a Fly Volume for the SQLite file, or switch to a managed DB.

## Option 4 — Railway (free trial credits)

1. https://railway.app → New Project → Deploy from GitHub repo.
2. Railway uses `Procfile`/`requirements.txt` automatically.
3. Add env vars. Note: free credits are limited; filesystem is ephemeral.

## Upgrading the database (recommended for production)

SQLite on ephemeral hosts loses data. For a durable free setup use a free
managed Postgres (Neon, Supabase, or ElephantSQL) and migrate the schema.
The app currently uses SQLite via `database.py`; swapping to Postgres requires
replacing `sqlite3` calls with `psycopg2`/SQLAlchemy. For a single church on
PythonAnywhere, staying on SQLite is simplest and durable.

## Environment variables

| Var | Required | Description |
|---|---|---|
| `SECRET_KEY` | yes | Flask secret key (32+ chars) |
| `JWT_SECRET` | yes | JWT signing secret (32+ chars) |
| `DATABASE_FILE` | no | Path to SQLite file (default `churchconnect.db`) |
| `PORT` | no | Port (default 5000; set by host) |
| `FORCE_HTTPS` | no | Redirect HTTP to HTTPS in production (`true`) |
| `FLASK_DEBUG` | no | `true`/`false` (default false) |

## First-run seeding

The app auto-creates tables on startup (`init_db()`). To populate sample data
once, run `python3 seed.py`. **Do not re-run in production** — it wipes all
tables.

## Health check

`GET /health` returns `{"status":"ok"}` for uptime monitors.
