# Design

The main decisions, why they were made, and what they cost. Setup and usage are in the [README](README.md).

## Shape

```
client ──HTTP :80──▶ nginx   rate limit on /auth, body ≤ 1 MB
                       │
                       ▼
                     api     uvicorn, FastAPI
                       │
                       ▼
                     db      Postgres 18, async SQLAlchemy 2 + psycopg 3

migrate (one-off): alembic upgrade head, then seed — runs before api starts
```

- **Code is grouped by feature** (`auth/`, `restaurants/`, `orders/`), each with its own models, schemas, service and router. Routers stay thin; business rules live in services; services raise domain errors that one handler maps to HTTP codes.
- **Admin code is split by scope.** Queries over all customers live in `AdminOrderService` and `AdminMenuService`, imported only by the admin routers. A customer route can't reach an all-orders query by accident, and a reviewer can check that by looking at imports.
- **The app is stateless**, so it can run as several replicas behind Nginx without changes.

## Orders

### Status is a state machine

Allowed moves are declared once, per role, in `app/orders/service.py`. Every change goes through them; anything else is `409`.

- **Admins send the target status** (`{"to": "accepted"}`), not "advance". An admin acting on a stale screen gets `409` instead of skipping a step.
- **The order row is locked** (`SELECT … FOR UPDATE`) while its status changes. Two admins accepting at once get one `200` and one `409`; the second request sees the status the first one set.
- **Every change is recorded** (from, to, who, when) in the same transaction.
- Cost: a short row lock per change, and one history row per change.

### Placing an order is idempotent

A double-click or a network retry must not create two orders.

- `POST /orders` requires an `Idempotency-Key` (a UUID the client makes per checkout).
- Requests with the same key take turns, using a Postgres advisory lock on (customer, key).
- **The key is looked up before the menu is checked.** A retry of an order that succeeded still succeeds, even if an item was sold out in between.
- Same key with the same body returns the original order (`200`); with a different body it's `422`.
- A unique index on (customer, key) is the last line of defence.
- Cost: clients must send a key.

### Orders don't change when the menu does

- Order lines copy the item's name and price; the order copies the delivery address.
- Totals are computed by the server from current prices. Prices or totals sent by the client are rejected.
- Menu items are never locked during placement. An item archived at the same moment can still be ordered at the price it had. That's accepted.

## Money and limits

- **Money is integer cents** (`*_cents`) in the database, in Python and in JSON. No floats anywhere. One currency (USD).
- **Limits are named constants** (`app/core/limits.py`): price per item, quantity, lines per order, delivery fee. Together they cap an order at 495,010,000 cents, which fits Postgres `INTEGER` (max 2,147,483,647). Raising a limit means checking that sum again.

## Auth

Custom auth with PyJWT and argon2 (`pwdlib`).

- **Access tokens** are JWTs valid for 15 minutes. The algorithm (HS256) is a code constant, never a setting, so configuration can't weaken verification. `exp` is required.
- **Role and `is_active` are read from the database on every request**, not trusted from the token. Demoting or deactivating someone takes effect at once. Cost: one primary-key lookup per request.
- **Login failures all look the same:** wrong password, unknown email and deactivated account get one `401`. An unknown email still runs a hash check against a dummy hash, so response time doesn't reveal which emails exist.
- **Password hashing runs in a thread pool**, since argon2 is slow by design and would otherwise block the event loop.
- **Signup can't create admins.** A `role` in the body is ignored; admins come from a CLI command with a prompted password.
- **Production refuses dev secrets.** With `ENVIRONMENT=production` the app won't start if the JWT key or database password is still a dev default, or if the JWT key is shorter than 32 bytes (the HS256 minimum).
- **Signup reveals whether an email is registered** (`409`). Accepted; hiding it needs email verification.

## IDs and pagination

- **Bigint primary keys inside, random `public_id` (UUIDv4) outside** for orders and users. Sequential ids would let anyone guess order URLs or count orders. Restaurants and menu items are public data and use plain ids.
- **Lists use cursor (keyset) pagination.** It stays fast at any depth, and new orders arriving at the top don't shift later pages.
- **Cursors hold only public values** (`created_at` + `public_id`, or name + id). A cursor is base64, which anyone can decode.
- Cost: no page numbers or totals.

## Menus

- **Nothing is deleted.** Items and categories are archived; items can also be marked sold out. Archive, un-archive and sold-out are fields on `PATCH`, not separate routes. Archiving a category hides its items without changing their own flags, so un-archiving brings them back as they were.
- **The admin menu view shows archived rows.** Un-archiving needs their ids, and the public menu hides them.
- **Names are unique**: categories within a restaurant, items within a category, ignoring case and including archived rows. A clash is `409`.
- **Every menu write locks the restaurant row first**, so two admins can't both create the same name at once. An order placed at the same restaurant waits for that edit to commit (its foreign key check needs the row); a menu write takes milliseconds.
- **A category from another restaurant is refused**; a composite foreign key enforces it.

## Transactions

Services commit explicitly before returning. The session dependency never commits: it closes the session, which discards anything uncommitted.

## Testing

- **Tests go through the HTTP API** against a real Postgres database. They assert on responses, not on tables or internals, so the code underneath can be rewritten without touching them.
- **Each test runs in a transaction that is rolled back.** Concurrency tests (two admins accepting one order, same-key orders, same-name menu writes) commit for real and use separate connections.

## Next steps

- Refresh tokens and logout: opaque tokens stored hashed, rotated on every use, and reuse of a rotated token revokes all of that user's tokens. Today clients log in again every 15 minutes.
- Real-time order status (push instead of polling), plus a live admin board.
- Restaurant management for admins (create, edit, deactivate).
- Restaurant opening hours.
- CI running lint and tests on every push.
