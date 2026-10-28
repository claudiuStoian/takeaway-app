# Takeaway API

Backend for a small takeaway platform. Customers browse restaurants, place orders and track them; admins manage menus and move orders through their statuses.

FastAPI · async SQLAlchemy 2 + psycopg 3 · PostgreSQL 18 · Alembic · Pydantic · Docker Compose · Nginx · Python 3.14

Design decisions: [`DESIGN.md`](DESIGN.md).

## Quick start

```bash
docker compose up --build
```

No `.env` needed; every setting has a development default (see `.env.example`). Compose starts Postgres, runs migrations, seeds demo data and serves the API behind Nginx on port 80:

- API docs (Swagger): http://localhost/docs
- Health check: http://localhost/health

The seed has 12 fictional restaurants and four demo users (skipped when `ENVIRONMENT=production`):

| Email | Password | Role |
|---|---|---|
| `admin1@example.com` | `admin1-demo` | admin |
| `admin2@example.com` | `admin2-demo` | admin |
| `customer1@example.com` | `customer1-demo` | customer |
| `customer2@example.com` | `customer2-demo` | customer |

In Swagger, log in, then paste the `access_token` into **Authorize**.

## Test UI (optional)

A small React app in `frontend/` for clicking through the API by hand. Manual testing only: not production code and not part of Compose. Needs Node 20.19+ or 22.12+ and the compose stack running:

```bash
cd frontend
npm ci
npm run dev
```

Open the URL Vite prints and use the demo-login buttons. The token is kept in `sessionStorage`, so each tab has its own login (e.g. admin in one, customer in another).

## API

| Area | Endpoints |
|---|---|
| Catalogue (public) | `GET /api/v1/restaurants` (`?cuisine=`) · `GET /api/v1/restaurants/{restaurant_id}/menu` |
| Accounts | `POST /api/v1/auth/signup` · `POST /api/v1/auth/login` · `GET /api/v1/me` |
| Orders (customer) | `POST /api/v1/orders` · `GET /api/v1/orders` · `GET /api/v1/orders/{public_id}` · `POST /api/v1/orders/{public_id}/cancel` |
| Admin: orders | `GET /api/v1/admin/orders` (`?status=`, `?restaurant_id=`) · `GET /api/v1/admin/orders/{public_id}` · `POST /api/v1/admin/orders/{public_id}/status` · `GET /api/v1/admin/orders/{public_id}/history` |
| Admin: menus | under `/api/v1/admin/restaurants/{restaurant_id}`: `GET /menu` · `POST /categories` · `PATCH /categories/{category_id}` · `POST /items` · `PATCH /items/{item_id}` |

Lists return `{"items": [...], "next_cursor": "..."}`; pass `?cursor=` for the next page (`null` means the end) and `?limit=` (1–100, default 20). Errors use FastAPI's `{"detail": ...}` shape.

### Order lifecycle

```
pending ──admin──▶ accepted ──admin──▶ out_for_delivery ──admin──▶ delivered
   │                  │
   ├─admin─────▶ rejected
   └─customer──▶ cancelled ◀──admin── (from accepted)
```

Any other move is `409`. Admins send the target status (`{"to": "accepted"}`), so a stale screen can't skip a step.

### Rules

- **Money** is integer cents (`price_cents`, `total_cents`), USD. The server computes all totals.
- **Orders keep a copy** of item names, prices and the delivery address; menu changes never alter past orders.
- **Nothing is deleted.** Items and categories are archived (`is_archived`) or marked sold out (`is_available`). `PATCH` changes only the fields sent.
- **Customers only see their own orders.** Someone else's order is `404`.
- **Signup always creates a customer.** Admins are created with the CLI (below).
- **Login and signup are rate-limited** by Nginx: 10 per minute per IP (burst of 5), then `429`.

### Known limitations

- **No refresh tokens or logout.** Access tokens last 15 minutes, then the client logs in again. See [`DESIGN.md`](DESIGN.md#next-steps).
- **No restaurant management API.** Restaurants come from the seed.
- **Order status is polled**, not pushed.
- **Plain HTTP locally.** Production needs HTTPS in front.
- **Passwords are 8–128 characters.** NIST SP 800-63B asks for 15 when the password is the only factor.

## Development

```bash
docker compose up -d db                  # Postgres on 127.0.0.1:5432
uv sync
uv run alembic upgrade head
uv run python -m app.cli seed            # safe to re-run
uv run uvicorn app.main:app --reload
```

If `uv sync` fails on `psycopg-binary` and the Python it picked ends in `+freethreaded`, uv chose a free-threaded build, which psycopg has no wheel for. Run `uv sync --python 3.14+gil` instead (this needs a regular Python 3.14 installed).

Create an admin (password is prompted; re-running for an existing admin changes nothing):

```bash
docker compose run --rm migrate python -m app.cli create-admin --email ops@example.com --full-name 'Ops'
```

### Tests

Functional tests through the HTTP API against a real Postgres database (`takeaway_test`), each in a rolled-back transaction.

```bash
uv run pytest               # needs the compose db running
uv run pytest --create-db   # drops and recreates the test database first
```

## Project layout

```
app/
  main.py        FastAPI app
  cli.py         seed, create-admin
  core/          config, database, security, pagination, limits, health check
  auth/          users, signup, login, current-user and admin dependencies
  restaurants/   restaurants and menus (admin routes in admin_router.py)
  orders/        orders and status changes (admin routes in admin_router.py)
alembic/         migrations
seed/            demo data
nginx/           reverse proxy config
tests/           functional tests and fixtures
frontend/        manual-testing UI
```

## How it was built

Built with assistance from Claude Code and Codex. I made the architecture
decisions, reviewed the generated code, and validated the implementation
through functional tests and manual testing.

[`DESIGN.md`](DESIGN.md) explains the main decisions and tradeoffs.
[`AGENTS.md`](AGENTS.md) records the domain rules and coding conventions
used to guide both agents.
