# AsyncPaymentProcessor

An asynchronous payment-processing microservice. It accepts a payment request over
HTTP, hands it off to a background pipeline built on RabbitMQ (gateway emulation +
persistence + webhook notification), and lets the client poll for the result.


## Contents

- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project layout](#project-layout)
- [Running it](#running-it)
- [API](#api)
- [Design notes](#design-notes)
- [Tests](#tests)
- [What's intentionally out of scope](#whats-intentionally-out-of-scope)


## Tech stack
**FastAPI + Pydantic v2**, **SQLAlchemy 2.0** (async),
**PostgreSQL**, **RabbitMQ** via **FastStream**, **Alembic**, **Docker /
docker-compose**. `httpx` + `tenacity` for outbound webhook delivery,
`prometheus-fastapi-instrumentator` for a `/metrics` endpoint.

## Project layout

```
src/app/
  api/            FastAPI routers + auth/DB dependencies
  core/           settings, logging
  db/             engine/session setup
  models/         SQLAlchemy ORM models (Payment, OutboxEvent)
  schemas/        Pydantic request/response models
  repositories/   data access, no business logic
  services/       PaymentService - the one place business rules live
  messaging/      RabbitMQ topology + event payload schemas
  workers/        outbox_relay, payment_consumer, gateway emulator
  webhooks/       webhook sender (retry + circuit breaker)
migrations/       Alembic, async-capable
tests/            pytest + pytest-asyncio, SQLite in-memory for speed
```

# Quick start


```bash
cp .env.example .env 
docker compose up --build
```
### Local development without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head

uvicorn app.main:app --reload --app-dir src 
python -m app.workers.outbox_relay 
python -m app.workers.payment_consumer
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```


## API
Every endpoint requires `X-API-Key`. The default (dev-only) key is `dev-api-key`,
set via the `API_KEY` env var / `docker-compose.yml`.
Interactive docs: `http://localhost:8000/docs`. Metrics: `http://localhost:8000/metrics`.

## Design notes

**Outbox pattern.** The payment row and its `outbox_events` row are written in
one DB transaction (`PaymentService.create_payment`), so "the payment was
accepted" and "an event will eventually reach RabbitMQ" can never diverge - there
is no window where one is true and the other isn't. A separate `outbox-relay`
process polls with `SELECT ... FOR UPDATE SKIP LOCKED` (so multiple relay
replicas could run concurrently without double-publishing) and marks rows
published only once RabbitMQ has confirmed them.

**Idempotency.** `idempotency_key` has a unique index. The service pre-checks
for an existing row (fast path for the common case), and if two requests race
past that check simultaneously, the unique constraint is the real guard - the
loser's `INSERT` fails, the service catches that specific `IntegrityError`,
rolls back, and returns the winner's row instead of a 500. Verified under real
concurrent load (5 parallel requests, same key → 1 row, 0 errors) during
development, not just by inspection.

**RabbitMQ retry / DLQ topology.** Rather than `nack` + immediate requeue
(which hot-loops a failing message), a failed message is explicitly republished
into one of two "parking lot" queues with a TTL. When the TTL expires, RabbitMQ
dead-letters it back onto the main exchange for another attempt:

```
payments.new --(fails)--> payments.retry.1 (TTL 2s) --> payments.new   (attempt 2)
payments.new --(fails)--> payments.retry.2 (TTL 4s) --> payments.new   (attempt 3)
payments.new --(3rd failure)-------------------------> payments.new.dlq (terminal)
```

This gives exponential-style backoff (2s, then 4s) without the
`rabbitmq-delayed-message-exchange` plugin. Attempt count travels in an
`x-retry-count` message header set explicitly by the consumer. See
`app/messaging/broker.py` for the full topology and the reasoning behind it.

A message-level retry is reserved for genuine technical faults (DB errors, an
exhausted webhook delivery, unhandled bugs) - **not** for a legitimately
declined payment. The 90/10 success/fail split from the gateway emulation is a
normal business outcome: it's always persisted and always triggers a webhook on
the first attempt, and never touches the retry/DLQ machinery.

**Webhook delivery.** `WebhookSender` retries transient HTTP failures with
`tenacity` (3 attempts, exponential backoff) and wraps each destination host in
a small circuit breaker: after enough consecutive failures it fails fast for a
cooldown window instead of piling up retries against a dead endpoint. If
delivery still can't complete after all of that, the failure is recorded on the
payment row (`webhook_delivered`, `webhook_last_error`) and propagates back up
into the RabbitMQ-level retry chain above - so a webhook endpoint that's merely
*slow to recover* gets a few more attempts, spaced minutes apart, before the
event lands in the DLQ.

**Auth.** Static `X-API-Key`, compared with `secrets.compare_digest` to avoid a
timing side-channel, applied via a FastAPI dependency on the whole router.
