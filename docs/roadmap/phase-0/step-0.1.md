---
phase: 0
step: "0.1"
title: Backend app skeleton
summary: A running FastAPI app in Docker Compose with typed .env settings (committed .env.dist), a Typer CLI entry point, CORS for the Vite dev origin, and GET /health — no database yet.
effort: 4
dependencies: none
---

# Step 0.1 — Backend app skeleton (FastAPI + Typer + Docker)

**Effort: 4** — pure runtime-app wiring, verifiable with zero infrastructure; persistence is deliberately deferred to step 0.2.

## Architect's outline

- `backend/pyproject.toml` managed with `uv`; pinned-minor deps: `fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]>=2`, `psycopg[binary]>=3`, `alembic`, `pydantic>=2`, `pydantic-settings`, `typer`, `python-ulid`, `sse-starlette` (declared now even if unused). Console script `app = app.cli.main:app`.
- `backend/app/core/config.py` — `Settings(BaseSettings)` via pydantic-settings: `DATABASE_URL`, `REDIS_URL`, `ENVIRONMENT`, `LOG_LEVEL`; loaded from `.env`.
- Commit `.env.dist` at repo root with placeholder values and a comment per key. **Do not create `.env`.** Before verification, stop and ask the user to `cp .env.dist .env` and adjust values; never write that file yourself.
- `backend/app/main.py` app factory; `GET /health` (process alive, no I/O). `/ready` is deliberately deferred to 0.2 (it needs PostgreSQL).
- `backend/app/cli/main.py` — Typer root app with a trivial `app version` command so the entry point is verifiable.
- `docker/backend.Dockerfile` (Python 3.12-slim, uv install); `compose.yaml` with a single `app-web` service (uvicorn `--reload`, bind mount). Structure the container start via an entrypoint script from day one (`exec uvicorn` for now) so 0.2 only prepends the migration call and the production image reuses it.
- CORS middleware allowing `http://localhost:5173` with credentials — needed so the 0.5 SPA can call `/health` in dev.
- Agent assignment: **backend-dev**.

## Verification

- `docker compose up -d`; `curl localhost:8000/health` → `{"status":"ok"}`.
- `docker compose exec app-web app version` prints the version (Typer entry point works).
- `.env.dist` is committed; no `.env` appears in the diff.

## Risks / notes

- Declaring SQLAlchemy/Alembic/psycopg deps now (unused until 0.2) is intentional — keeps 0.2 a pure wiring step with no dependency churn.
- The agent must halt and request `.env` creation from the user rather than fabricating one, even though Phase-0 values are non-secret. `.env` will later hold the OpenRouter API key, so the rule is absolute.
