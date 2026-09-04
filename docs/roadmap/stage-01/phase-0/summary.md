# Phase 0 — Foundations

**Goal:** Both apps run locally via Docker Compose and talk to each other.

## Delivered

- FastAPI backend with typed settings — Python 3.12, `uv` deps, config from
  `.env` with a committed `.env.dist` documenting every key.
- `GET /health` (liveness, no I/O) and `GET /ready` (503 when PostgreSQL is
  unavailable).
- Typer CLI entry point (`app version`) — one operator surface next to the web
  app.
- PostgreSQL 16 + pgvector and Redis as Compose services with healthchecks.
- Async session wiring and an Alembic baseline whose only change enables
  pgvector; migrations run automatically at container start.
- `app openapi export` — schema dump without a running server, the backend half
  of the typed-client pipeline.
- React SPA (Vite + TypeScript, MUI theming with system/light/dark persisted,
  routing shell, data fetching, i18n) as its own Compose service.
- Generated typed API client (types committed) plus a home widget showing live
  backend status.

## Non-obvious decisions

- Readiness checks PostgreSQL but deliberately not Redis — a broker outage must
  not take the HTTP app out of rotation.
- Agents never create `.env`; they stop and ask — that file later holds the
  OpenRouter key.
- Frontend calls the backend cross-origin via CORS, not a Vite proxy — exercises
  the cookie/CORS path Phase 1 auth depends on.
- Entrypoint scripted from step one; later steps only prepend to it.
- MUI v6+ and React Router v7 package names pinned up front — avoids a theming
  workaround and an import rewrite later.
- OpenAPI export kept free of database access — codegen works with the database
  stopped.
- Frontend backend URL lives in Compose, not `.env` — configuration, not secret.
- DB/migration/driver deps declared in 0.1 though unused until 0.2 — no
  mid-phase dependency churn.

## Not delivered / deferred

- Taskiq worker — Redis added as broker infrastructure only; worker in Phase 2.
- Domain tables — Phase 2; Phase 0 ships base model conventions only.
- Auth, route guards, CSRF header slot in the API client — Phase 1.
- CI enforcement that committed generated types stay in sync — left as a manual
  regenerate-and-diff convention in the QA checklist.
- Locales beyond English — wiring and English strings only.

> Source note: `roadmap.md` describes Phase 0 as two steps; the phase folder has
> five (0.1–0.5). This summary follows the step files.
