# Takeaway API

Backend for a small takeaway platform. Customers browse restaurants and menus, place orders and track them; staff (admins) manage menus and move orders through their statuses.

FastAPI · async SQLAlchemy 2 + psycopg 3 · PostgreSQL 18 · Alembic · Pydantic · Docker Compose · Nginx · Python 3.14

> **Status:** public catalogue, accounts (signup, login, roles), customer orders and admin order handling. Admin menu management lands next.

## Quick start

```bash
docker compose up --build
```

No `.env` needed — every setting has a development default (see `.env.example`). Then open:

- API docs (Swagger): http://localhost/docs
- Health check: http://localhost/health — `200` when the API can reach the database, `503` otherwise

Compose starts Postgres, runs migrations and seeds demo data once (`migrate`), then the API (`uvicorn --workers 2`) behind Nginx. Only Nginx is published (port 80); Postgres listens on `127.0.0.1:5432` for local development.

Seed data: 12 fictional restaurants with categorised menus in USD (`seed/restaurants.json`) and four demo users (`seed/users.json`). Each is inserted only when its table is empty, so re-running never overwrites edits. Demo users are **never** seeded with `ENVIRONMENT=production` — their passwords are public:

| Email | Password | Role |
|---|---|---|
| `admin1@example.com` | `admin1-demo` | admin |
| `admin2@example.com` | `admin2-demo` | admin |
| `customer1@example.com` | `customer1-demo` | customer |
| `customer2@example.com` | `customer2-demo` | customer |

```bash
curl -s localhost/api/v1/restaurants
curl -s 'localhost/api/v1/restaurants?cuisine=thai'
curl -s localhost/api/v1/restaurants/1/menu
```

## API overview

| Area | Endpoints |
|---|---|
| Catalogue (public) | `GET /api/v1/restaurants` (cursor, `?cuisine=`) · `GET /api/v1/restaurants/{restaurant_id}/menu` |
| Accounts | `POST /api/v1/auth/signup` · `POST /api/v1/auth/login` · `GET /api/v1/me` |
| Orders (customer) | `POST /api/v1/orders` (`Idempotency-Key` required) · `GET /api/v1/orders` (mine, cursor) · `GET /api/v1/orders/{public_id}` · `POST /api/v1/orders/{public_id}/cancel` |
| Admin — orders | `GET /api/v1/admin/orders` (cursor, `?status=`, `?restaurant_id=`) · `POST /api/v1/admin/orders/{public_id}/status` `{"to": "<status>"}` · `GET /api/v1/admin/orders/{public_id}/history` |

Lists return `{"items": [...], "next_cursor": "..."}`; pass `?cursor=` for the next page (`null` = end) and `?limit=` (1–100, default 20). Errors use FastAPI's `{"detail": ...}` shape.

The menu lists only what a customer can order or see: inactive restaurants are `404`, archived categories and items are hidden, and sold-out items stay listed with `"is_available": false`. Money is integer cents (`*_cents`), USD.

### Order lifecycle

```
pending ──admin──▶ accepted ──admin──▶ out_for_delivery ──admin──▶ delivered
   │                  │
   ├─admin─────▶ rejected
   └─customer──▶ cancelled ◀──admin── (from accepted)
```

Any other move is `409`, including a repeat of the current status. The status endpoint takes the **target** status, never "next": an admin acting on a stale screen gets `409` instead of skipping a step, and two admins accepting the same order at once get one `200` and one `409`. Every change is recorded with who made it and when (`…/history`).

## Auth

```bash
curl -s localhost/api/v1/auth/signup -H 'Content-Type: application/json' \
  -d '{"email": "sam@example.com", "password": "correct-horse", "full_name": "Sam"}'
TOKEN=$(curl -s localhost/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email": "sam@example.com", "password": "correct-horse"}' | jq -r .access_token)
curl -s localhost/api/v1/me -H "Authorization: Bearer $TOKEN"
```

In Swagger, log in, then paste the `access_token` into **Authorize**.

- **Signup** always creates a `customer` (a `role` in the body is ignored) and returns `201` with the user; a registered email is `409`. Passwords are 8–128 characters; emails are stored lowercased.
- **Login** returns a 15-minute access token (JWT, HS256). Wrong password, unknown email and deactivated account all get the same `401`.
- **Every request** re-reads the user's role and `is_active` from the database, so demotion or deactivation applies immediately. Admin-only endpoints are `403` for customers.
- **Admins** are created with the CLI, never through the API. The password is prompted, never passed as an argument; re-running for an existing admin changes nothing:
  ```bash
  docker compose run --rm migrate python -m app.cli create-admin --email ops@example.com --full-name 'Ops'
  ```
- **Rate limit:** Nginx allows 10 login/signup requests per minute per IP (burst 5), then `429`.
- **Not yet:** refresh tokens and logout — clients log in again when the token expires.
- **Transport:** passwords and tokens travel in plain text inside the request body and headers; local compose serves plain HTTP. Production needs HTTPS (TLS at Nginx or a load balancer).

With `ENVIRONMENT=production`, the app refuses to start while `JWT_SECRET_KEY` or `DB_PASSWORD` still has its development default, or when `JWT_SECRET_KEY` is shorter than 32 bytes (the HS256 minimum, RFC 7518 §3.2).

## Development

```bash
docker compose up -d db                  # Postgres on 127.0.0.1:5432
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed            # idempotent
uv run python -m app.cli create-admin --email you@example.com --full-name 'You'
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
  cli.py         operational commands (seed, create-admin)
  core/          config, db session, errors, security (hashing, JWT), pagination, limits, health check
  auth/          users, roles, signup, login, current-user and admin dependencies
  restaurants/   restaurants, categories, menu items
  orders/        orders, items, status transitions, history; admin routes in admin_router.py
alembic/         migrations
seed/            demo data (restaurants.json, users.json)
nginx/           reverse proxy config
tests/           fixtures (test DB, rolled-back session, HTTP client)
```

Each feature folder holds `models.py`, `schemas.py`, `service.py`, `router.py`; routers call services, services call models.
