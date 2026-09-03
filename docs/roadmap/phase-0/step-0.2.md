---
phase: 0
step: "0.2"
title: Database, migrations, readiness
summary: Add PostgreSQL 16 + pgvector and Redis to Compose, wire async SQLAlchemy and the Alembic baseline (CREATE EXTENSION vector), run migrations on startup, and add GET /ready.
effort: 4
dependencies: ["0.1"]
---

# Step 0.2 — Database, migrations, readiness

**Effort: 4** — a self-contained persistence slice with its own known friction (async Alembic + psycopg 3); crisp pass/fail via `/ready` and `alembic current`.

## Architect's outline

- `compose.yaml`: add `postgres` (`pgvector/pgvector:pg16` image, healthcheck) and `redis` (broker-only, zero app coupling — Taskiq worker code is step 2.2); `app-web` gets `depends_on: condition: service_healthy`.
- `backend/app/db/session.py` — async engine + `async_sessionmaker` + `get_db_session` FastAPI dependency (plain `Depends()`, no DI container).
- `backend/app/db/models/base.py` — SQLAlchemy 2 `DeclarativeBase` with naming conventions and a ULID-string PK mixin; no domain tables yet.
- `backend/alembic/` — async-template Alembic wired to settings + metadata; one baseline migration whose only DDL is `CREATE EXTENSION IF NOT EXISTS vector` (proves pgvector and migration plumbing without inventing Phase-2 schema).
- Extend the 0.1 entrypoint script to `alembic upgrade head && exec uvicorn` (works with `--reload`; not a compound CMD).
- `GET /ready` — runs `SELECT 1` against PostgreSQL; Redis deliberately not checked (a broker outage must not make the HTTP app unready).
- `.env.dist` already declares `DATABASE_URL`/`REDIS_URL` (0.1); if the user's `.env` predates needed value changes, stop and ask the user to update it — never edit `.env` yourself.
- Agent assignment: **backend-dev**.

## Verification

- `docker compose up -d`; `/ready` → 200; stopping postgres flips `/ready` to 503.
- `alembic current` shows the baseline revision; `psql … "\dx vector"` shows pgvector installed.

## Risks / notes

- Alembic async-engine setup with psycopg 3 is a known friction point; use the async Alembic template from the start.
