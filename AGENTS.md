# AGENTS.md Guidelines

Always read this page first.

## Immediate Checklist
- **NEVER delete anything — files, DB rows, databases, Docker volumes — without asking the user first.** Applies in every permission mode. This includes `alembic downgrade` and `docker compose down -v`.
- Target Python 3.14+; no backward-compatibility workarounds.
- Manage dependencies with `uv`.
- Code to Google style, prefer modern Python syntax, and skip inline comments unless code is opaque.
- Never use a broad `except` clause unless the situation specifically requires it. Only catch known exceptions, when necessary.
- Never use local imports.
- Use single quotes for strings, except when the string represents a message/phrase.
- Only write docstrings for non-obvious classes/functions; otherwise rely on clear naming.
- Define helper functions below the main entrypoint/public API, ordered by call sequence.
- When executing arbitrary code locally, don't use bare `python -c "..."`; use `uv run python -c "..."` so the project's environment is active.
- After finishing a logical chunk of work (not after every edit), run `uv run ruff check --fix <changed_files>` and `uv run ruff format <changed_files>`.
- Never read or source `.env` files. Ask the user for specific values.

## Project shape

Backend for a small takeaway platform. Customers browse restaurants and menus, place orders, and track order status. Staff (`admin` role) manage menus and move orders through their statuses. Backend, plus a small React UI in `frontend/` for manual testing only; it is not production code and is not part of Docker Compose.

- **Stack:** Python 3.14; FastAPI (async endpoints); PostgreSQL 18 (in Docker Compose) via async SQLAlchemy 2 (`AsyncSession`, psycopg 3) with Alembic migrations; separate Pydantic request/response schemas (not SQLModel); custom JWT auth (PyJWT + `pwdlib[argon2]`); `pydantic-settings` for config; Docker Compose; Nginx as reverse proxy in front of `uvicorn`.
- **Feature-first layout.** Group code by domain feature, not technical role. Each feature is a co-located folder — `app/auth/` (users, roles, login, tokens), `app/restaurants/` (restaurants, menus, menu items), `app/orders/` (orders, order items, status transitions) — holding its own `models.py`, `schemas.py`, `service.py`, and `router.py` where applicable. Cross-cutting infrastructure lives in `app/core/` (`config.py`, `db.py`, `security.py`, `exceptions.py`, `pagination.py`, `limits.py`, `health.py`). Routers handle HTTP only (auth dependencies, schemas, status codes) and never query the database or make business decisions; those live in `service.py`. Importing a domain enum or model type across layers is fine.
- **Admin code is split by scope.** Queries across all customers live only in a feature's `admin_service.py` (`AdminOrderService`, `AdminMenuService`), imported only by its `admin_router.py`. Customer routes never import an admin service.

## Domain rules

- **Order status is a state machine.** Allowed transitions are declared once, per role (`CUSTOMER_TRANSITIONS`, `ADMIN_TRANSITIONS` in `app/orders/service.py`), and every status change goes through them; an illegal transition is a `409`, never a silent overwrite. Flow: `pending → accepted → out_for_delivery → delivered`; admins can reject a pending order or cancel an accepted one; customers can cancel a pending one.
- **Order items snapshot price and name** at order time; orders snapshot the delivery address. Editing or removing a menu item never changes past orders.
- **Idempotent where a retry is expected:** seeds, CLI commands, migrations' data steps, and order placement. Running them twice must not duplicate or overwrite data. Status changes are not idempotent: repeating one is an illegal transition (`409`).
- **Soft delete only.** Menu items use `is_available` / `is_archived`, categories `is_archived`; an item is visible and orderable only if neither it nor its category is archived. No hard-delete endpoints, jobs or cascades in code.
- **Integrity in the DB where it can live there:** composite FK keeps an item's category in the same restaurant; `CHECK`s on prices/quantities; unique `(order_id, menu_item_id)`. Upper limits are named constants in `app/core/limits.py`, validated in schemas — raising them means re-checking that order totals still fit `INTEGER`.
- **Money is never a float.** Integer cents everywhere (DB, Python, JSON); every money field ends in `_cents`. Single currency (USD).
- **Totals are computed server-side** from current menu prices. Never trust a price or total sent by the client.
- **Order placement is idempotent.** `POST /orders` requires an `Idempotency-Key` header, unique per customer. Same-key requests are serialized with `pg_advisory_xact_lock`, and the key is looked up **before** menu validation; a repeat with the same body returns the original order, a different body is `422`.
- **Ownership is enforced in the service layer.** A customer only ever sees and acts on their own orders; a wrong-owner lookup returns `404`, not `403`, so IDs aren't confirmable.
- **Roles:** `customer` and `admin`. Admin-only endpoints declare it with a dependency (`require_admin`), never with an inline `if`.

## Naming across layers

Field names are identical across SQLAlchemy models, Pydantic schemas, and API query/path params. The model column/table name is the authority. When adding a field or entity, check the model first and carry that name through.

Model classes are singular (`User`, `MenuItem`); tables are plural snake_case (`users`, `menu_items`), and constraint/index names follow the table. This also keeps Postgres reserved words (`user`, `order`) out of table names — check new names against `pg_get_keywords()`.

## Style guide

Code should read like a person wrote it: descriptive names, short functions that read top-down as a sequence of named steps, few comments.

- Walrus (`:=`) for check-then-use; `with suppress(...)` over try/except-pass; module-level `logger = getLogger(__name__)`; modern type hints (`X | None`, `list[X]`); f-strings.
- Comments explain *why*, in one short line. No module essays, no docstrings that narrate what the code already says.
- Business logic lives in stateless namespace classes, never instantiated: `XxxService`. The public `@classmethod` comes first and reads top-down as a sequence of named steps — extract a step into a helper only when it has substance (a query, a validation, a calculation), not to wrap one or two statements; `_`-prefixed `@staticmethod` helpers follow below it, in call order. Drop the class noun from method names — `OrderService.place`, not `place_order`. Shared pure utilities stay module-level.
- What stays a function: FastAPI endpoints, dependencies, and single pure utility functions.
- Routers stay thin: declare auth dependencies, response model, and status code, then call one service method. Input validation lives in Pydantic schemas.
- Services raise domain exceptions (`OrderNotFound`, `InvalidStatusTransition`); a single exception handler maps them to HTTP responses. Services don't import `HTTPException`.
- Async rules: every relationship is `lazy='raise'` and queries load what they need with `selectinload` / `joinedload`. Never call blocking code in `async def`; CPU-bound work (argon2) goes through `fastapi.concurrency.run_in_threadpool`.
- When a module grows too big, split it into a package (`models/`, `services/`) rather than a giant file.

## Naming

- **Methods are descriptive verb phrases** that read as a sentence at the call site — `AdminOrderService.change_status`, `AdminMenuService.update_item`.
- **Class suffixes state the role**, domain first: `XxxService`, `XxxSettings`.
- **Pydantic schemas are `Request` / `Response`.** Request bodies are `<Thing><Action>Request` (`OrderPlaceRequest`, `MenuItemUpdateRequest`); a nested part is `<Thing>Request`; auth actions with no entity use the action alone (`SignupRequest`, `LoginRequest`). Responses are `<Thing>Response`, lists `<Thing>PageResponse`. Staff views take the `Admin` prefix (`AdminOrderResponse`). Seed-file inputs end in `Seed`. A response that adds fields to another extends it rather than repeating them.
- **Booleans** start with `is_` / `has_` / `should_` (`is_available`, `is_active`).
- **Datetime fields** end in `_at` (`created_at`, `updated_at`) and are timezone-aware UTC.
- **Enums** are `StrEnum`s defined next to their model (`OrderStatus.OUT_FOR_DELIVERY`).
- **Thresholds and limits** are named constants (`ACCESS_TOKEN_TTL_MINUTES`, `MAX_LINES_PER_ORDER`). No magic numbers.

## Security

- Secrets (JWT signing key, DB password) come from env vars via `pydantic-settings`. Code holds only development placeholders, which the app refuses when `ENVIRONMENT=production`. Real secrets are never committed, never logged.
- Passwords are hashed with argon2 (`pwdlib`); never stored or logged in plain text. Hashing and verification run via `run_in_threadpool`.
- JWT: short-lived access tokens; the algorithm is a code constant (`JWT_ALGORITHM`), never a setting, and is passed explicitly on decode; `exp` is required. The user's role and `is_active` are re-read from the DB, not trusted from the token.
- **Transactions:** service write methods end with an explicit `await session.commit()` before returning. The session dependency is `Depends(..., scope="function")`, never commits, and closing it discards anything uncommitted — a `yield` dependency's default exit runs after the response is sent. Security writes that must survive an error are committed **before** raising.
- All DB access goes through SQLAlchemy with bound parameters; no f-string SQL.
- Order and user bigint ids never leave the server: routes, responses, tokens and pagination cursors use `public_id`. Base64 is not secrecy — never put an internal id in a cursor.
- Response schemas are explicit allow-lists — never return ORM objects that could leak `hashed_password` or other users' data.

## Testing

- Functional tests through the HTTP API (`httpx.AsyncClient` + `ASGITransport`, `@pytest.mark.anyio`) against the real `takeaway_test` Postgres DB are the default; unit tests only for pure logic with many edge cases.
- Each test runs in a rolled-back transaction (session joined with `join_transaction_mode='create_savepoint'`); override the session via `app.dependency_overrides`.
- **No test may assume an empty database** — assert on rows the test created. Never add truncate/delete cleanup.
- Run with `uv run pytest` (compose `db` must be up). The test DB is kept between runs. `uv run pytest --create-db` drops and recreates it — **never run it without asking the user first.**

## Migrations

- Every schema change ships with an Alembic migration: `uv run alembic revision --autogenerate -m '<short message>'`, then read and fix the generated file before applying.
- Never edit a migration that has already been applied; add a new one.
- Never run `alembic downgrade` without asking first.
