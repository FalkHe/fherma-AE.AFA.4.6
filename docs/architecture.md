# Architecture

Current state, facts only. The conceptual map — layer boundaries, planned
components, wire convention, session model — is
[general/architecture.md](general/architecture.md); this page is the short
index agents read first. `docs/README.md` indexes everything else.

State: **scaffolding**. Docker environment, modular backend/frontend
skeletons and username/password authentication exist. The game agent does not.

## Tech stack

- Python 3.12 · FastAPI · Typer (`app` CLI) · SQLAlchemy 2 (async) · Alembic · Pydantic 2 · structlog
- PostgreSQL (pgvector) → application state; SRD rule chunks and embeddings for RAG, loaded by `app srd ingest`
- OpenRouter → every LLM call, through the `core/llm/` seam; LangChain carries chat, images go direct through the OpenRouter SDK, LangGraph provides the checkpointer that persists agent state
- TypeScript · React 19 · Material UI 9 · Vite · TanStack Query · React Router · react-i18next
- Tooling: `uv` + ruff + pytest (backend), `pnpm` + ESLint + `tsc` + Vitest (frontend)
- No background job runner and no Redis: every operation is request-scoped or a CLI one-off

## Structure

- `backend/app/core/` → settings, logging, security primitives, db session
- `backend/app/api/v1/router.py` → combines the modular routers, nothing else
- `backend/app/modules/<module>/` → `models.py schemas.py routes.py service.py` (today: `auth`, `users`, `health`)
- `backend/tests/<module>/` → mirrors `modules/` one-to-one
- `backend/alembic/` → migrations; `app-web` runs `alembic upgrade head` on boot
- `frontend/src/core/` → theme, config, api client, i18n setup, the shared app frame (`layout/`)
- `frontend/src/modules/<module>/` → `components/ hooks/ routes/` (today: `auth`, `playthrough`)
- `frontend/src/api/schema.d.ts` → generated from the backend's OpenAPI, committed
- `docs/general/` → system-wide docs · `docs/modules/` → one subsystem each · `docs/roadmap/` → history
- `docs/intents/` → fhit intents and sprints
- `docs/roadmap/` → old development roadmap, never write, only read phases.md and treat each phase as intent 

## Conventions

- Modules own their layer stack; `core/` holds only what a second module already calls, promoted unchanged.
- Cross-module access goes through the other module's `service.py` / `models.py` — never its internals.
- Services are modules of functions, not classes. No repository classes, no ORM relationships.
- Services own the transaction boundary; `get_db_session` never commits.
- camelCase on the wire via a shared Pydantic base; resource objects returned directly, no envelope.
- One error envelope for every non-2xx: `{"error": {"code", "message", "details"}}`. Domain codes carry the meaning; the frontend maps `code` to an i18n key and never shows `message`.
- Auth: Argon2 passwords, opaque server-side sessions hashed at rest, HttpOnly cookie, CSRF synchroniser token in a response header. One implicit `user` role.
- Backend tests are synchronous (TestClient / Typer `CliRunner`) and never build a real engine, except opt-in tests marked `database`, which build one against a scratch Postgres database and skip cleanly when none answers (`make backend-test-db`, vs. plain `make backend-test`); warnings are errors.

## Infrastructure

- `compose.yaml` → `app-web` (uvicorn :8000), `frontend` (Vite :5173), `postgres` (pgvector), plus `app-cli` / `node-cli` behind the `cli` profile for lint and tests with the stack down
- Langfuse tracing → external instance, configured by the three `LANGFUSE_*` variables in `.env`; blank means off (`backend/app/core/tracing/`)
- Root `Makefile` wraps every common operation; `make help` lists them
- CI: `<TODO>`
- Environments beyond local dev: `<TODO>`
