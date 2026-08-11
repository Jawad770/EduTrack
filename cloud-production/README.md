# EduTrack Cloud — deploy to Onairo VPS (PostgreSQL 16)

## Database

| Environment | `DATABASE_URL` |
|-------------|----------------|
| **Production (VPS)** | `postgresql+psycopg2://USER:PASSWORD@127.0.0.1:5432/edutrack_cloud` |
| **Local development** | `sqlite:///./cloud_accounts.db` (default) |

- Set `REQUIRE_POSTGRES=true` on the VPS so startup refuses SQLite.
- If PostgreSQL is unreachable, startup **raises** — there is no silent SQLite fallback.

## Run locally (SQLite)

```bash
cd cloud
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8100
```

## Production (PostgreSQL)

1. Create DB/role on PostgreSQL 16.
2. Copy `.env.example` → `.env` and set `DATABASE_URL`, `REQUIRE_POSTGRES=true`, SMTP, JWT, admin key.
3. Place entitlement **private** key at `ENTITLEMENT_PRIVATE_KEY_PATH` (never commit it).
4. Install deps and start:

```bash
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8100
```

## Tests

```bash
cd cloud
pytest -q
# Optional against Postgres:
# set DATABASE_URL=postgresql+psycopg2://… && pytest -q
```

## Admin generate license

```bash
curl -X POST http://127.0.0.1:8100/v1/admin/licenses/generate \
  -H "X-Admin-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"plan\":\"professional\"}"
```

Keys are shown once. Duration is always 365 days from `issued_at`.
