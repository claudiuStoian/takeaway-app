# Takeaway API

Backend for a small takeaway platform. Customers browse restaurants and menus, place orders and track them; staff (admins) manage menus and move orders through their statuses.

FastAPI · async SQLAlchemy 2 + psycopg 3 · PostgreSQL 18 · Alembic · Pydantic · Docker Compose · Nginx · Python 3.14

> **Status:** public catalogue (restaurants and menus) with seed data. Accounts and ordering land next.

## Quick start

```bash
docker compose up --build
```

No `.env` needed — every setting has a development default (see `.env.example`). Then open:

- API docs (Swagger): http://localhost/docs
- Health check: http://localhost/health — `200` when the API can reach the database, `503` otherwise

Compose starts Postgres, runs migrations and seeds demo data once (`migrate`), then the API (`uvicorn --workers 2`) behind Nginx. Only Nginx is published (port 80); Postgres listens on `127.0.0.1:5432` for local development.

Seed data: 12 fictional restaurants with categorised menus in USD (`seed/restaurants.json`). It is inserted only when the catalogue is empty, so re-running never overwrites edits.

```bash
curl -s localhost/api/v1/restaurants
curl -s 'localhost/api/v1/restaurants?cuisine=thai'
curl -s localhost/api/v1/restaurants/1/menu
```

## API overview

| Area | Endpoints |
|---|---|
| Catalogue (public) | `GET /api/v1/restaurants` (cursor, `?cuisine=`) · `GET /api/v1/restaurants/{restaurant_id}/menu` |

Lists return `{"items": [...], "next_cursor": "..."}`; pass `?cursor=` for the next page (`null` = end) and `?limit=` (1–100, default 20). Errors use FastAPI's `{"detail": ...}` shape.

The menu lists only what a customer can order or see: inactive restaurants are `404`, archived categories and items are hidden, and sold-out items stay listed with `"is_available": false`. Money is integer cents (`*_cents`), USD.

With `ENVIRONMENT=production`, the app refuses to start while `JWT_SECRET_KEY` or `DB_PASSWORD` still has its development default.

## Development

```bash
docker compose up -d db                  # Postgres on 127.0.0.1:5432
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed            # idempotent
uv run uvicorn app.main:app --reload
```

### Tests

```bash
uv run pytest               # functional tests via the HTTP API against real Postgres
uv run pytest --create-db   # drop and recreate the test database first
```

Tests use a separate `takeaway_test` database in the compose Postgres. It is created on first use, migrated to the latest revision, and kept between runs; each test runs in a transaction that is rolled back.

## Project layout

```
app/
  main.py        FastAPI app
  cli.py         operational commands (seed)
  core/          config, db session, errors, pagination, limits, health check
  restaurants/   restaurants, categories, menu items
alembic/         migrations
seed/            demo data (restaurants.json)
nginx/           reverse proxy config
tests/           fixtures (test DB, rolled-back session, HTTP client)
```

Each feature folder holds `models.py`, `schemas.py`, `service.py`, `router.py`; routers call services, services call models.
