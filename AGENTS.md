# AI Dungeon Master

A single-player D&D (5e SRD) game run entirely by an AI agent: it narrates,
interprets free-form actions, rolls dice, looks up rules and keeps state.

## Commands

Everything runs in Docker; no host Python/Node toolchain is required.

- Install: `cp .env.dist .env && make build`
- Dev services: `make up` (frontend :5173, API :8000, postgres) · `make down`
- Lint / format: `make lint` (`make backend-lint` = ruff check + format check · `make frontend-lint` = ESLint)
- Tests (all): `make test` · backend only: `make backend-test` · frontend only: `make frontend-test`
- Tests (single file): `docker compose run --rm --no-deps app-cli pytest tests/<path>` · `docker compose run --rm --no-deps node-cli pnpm test <path>`
- Tests (opt-in, real database): `make backend-test-db` — starts postgres, runs the `database`-marked tests against a scratch database
- Type check: `make frontend-typecheck`
- Typed API client: `make generate-api` (stack must be up)
- `make help` lists every target.

## Structure

See `docs/architecture.md`. Module READMEs are the source of truth per module.

Both trees are organised by domain **module**, not by technical layer:

```
backend/app/modules/<module>/     models.py schemas.py routes.py service.py
backend/tests/<module>/           mirrors the above one-to-one
frontend/src/modules/<module>/    components/ hooks/ routes/
```

`core/` on either side holds only what two or more modules need.

## Workflow

Intents and sprints live in `docs/intents/` (fhit plugin: `/fhit:intent`, `/fhit:backlog`, `/fhit:sprint`, `/fhit:status`).

Project docs are indexed in `docs/README.md`. `docs/roadmap/` is history, not
current state — where a roadmap doc and the code disagree, the code wins.

## Rules

- Content / reasoning / mechanics stay separate: the LLM never fakes a roll and never edits state directly — it calls a tool. Only SRD rules text goes through RAG.
- `135.md` is the binding brief; `docs/general/requirement-map.md` maps it onto the system. Keep every graded criterion satisfiable.
- Services are modules of functions, not classes. Call them as `from . import service` then `service.foo(...)` — importing by name breaks the suite's monkeypatching.
- Services own the transaction boundary; routes contain no `commit`, `add` or `execute`.
- A helper is promoted to `core/` only once a **second** module calls it, unchanged.
- One module never imports another module's internals — only its `service.py` / `models.py`.
- camelCase on the wire; one error envelope `{"error": {"code", "message", "details"}}` with stable domain codes.
- Every user-facing string goes through a react-i18next key. No literal copy in components.
- LLM access goes through OpenRouter — never straight to a vendor API.

## Gotchas

- `.env` is required (`cp .env.dist .env`; every default works). Ports 5173 and 8000 must be free.
- Run `make build` after any dependency change; `make rebuild` also renews the frontend `node_modules` volume.
- `frontend/src/api/schema.d.ts` is generated and committed — never hand-edited.
- Backend pytest runs with `filterwarnings = ["error"]`: any warning fails the suite.
- Tests must never build a real DB engine — `backend/tests/conftest.py` stubs the DB session and pins env vars so the root `.env` cannot leak in. One opt-in exception: tests marked `database` (`backend/tests/srd/conftest.py`) build a real engine against a scratch database and skip cleanly when no Postgres answers.
- Vitest has no globals: import vitest APIs explicitly. Fetch is stubbed by one dispatcher installed at startup (`frontend/src/test/`), because openapi-fetch captures `fetch` at import time.
- No background job runner and no Redis: every operation is request-scoped or a Typer CLI one-off.
- `OPENROUTER_API_KEY` is read by the `core/llm/` seam (`app llm chat`); without it every model call fails naming the variable. Optional Langfuse tracing is enabled per checkout via `COMPOSE_FILE` in `.env`.
- `make langfuse-down` uses `stop`, never `down` — `down` would tear down the whole project and can delete the dev database.
