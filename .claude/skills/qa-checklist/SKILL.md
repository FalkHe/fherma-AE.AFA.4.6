---
name: qa-checklist
description: Conventions and known traps to check when changing this repo — generated API types drifting, the modular layout, and the lru_cache'd async engine vs pytest event loops. Use when reviewing or landing backend/frontend changes, adding tests, or touching FastAPI routes and response models.
---

# QA checklist

Conventions to check before and after a change, plus known rough edges. Not
enforced by CI.

## Generated API types must never drift

`frontend/src/api/schema.d.ts` is generated from the backend's OpenAPI schema
and committed. After any change to a FastAPI route, a request/response model, or
anything else affecting `app.openapi()`:

```bash
make generate-api    # or, with host pnpm: cd frontend && pnpm generate:api
git diff --exit-code frontend/src/api/schema.d.ts
```

- `make generate-api` needs the stack running (`make up`): it exports the schema
  from `app-web`, then runs `openapi-typescript` in a one-off `node-cli`
  container — no host Node required.
- A reported diff means the committed types were stale; commit the regenerated
  file.
- No diff means the schema didn't actually change, or was already regenerated.

Watch for the reverse case too: a frontend type declared locally as a stand-in
for a payload the backend does not send yet. Delete the stand-in when the real
field lands; never build on one.

## Keep modules self-contained

Both trees are organised by domain module, not by technical layer (see
`.claude/CLAUDE.md`). When reviewing a change, check that it did not quietly
re-centralise:

- A backend module's models, schemas, routes and service stay under
  `app/modules/<module>/`. `app/api/v1/router.py` only wires routers together.
- `app/core/` and `frontend/src/core/` are for code with **two or more**
  module callers. A single-caller helper belongs to that caller.
- One module must not import another module's `service.py` internals; go
  through its public surface, or the dependency belongs in `core/`.
- `backend/tests/<module>/` mirrors `backend/app/modules/<module>/` one to one.

## `lru_cache`'d async engine — pytest event-loop trap

The async engine and session factory in `backend/app/core/` are cached with
`@lru_cache`, keyed process-wide rather than per event loop. That is correct for
the running app (one loop for the process lifetime) but breaks async pytest
fixtures: reusing an engine created on a previous loop raises "Future attached
to a different loop" or hangs silently.

If you add fixtures that touch the database, either:

- call `get_engine.cache_clear()` and `get_sessionmaker.cache_clear()` around
  tests that get a fresh event loop, or
- build a dedicated engine/sessionmaker in the fixture instead of going through
  `get_engine()` / `get_sessionmaker()`.

**The current suite sidesteps this entirely** and should keep doing so: it is
fully synchronous (TestClient / Typer `CliRunner`) and overrides the
`get_db_session` dependency with a stub, so no real engine is ever constructed.
`tests/conftest.py` also pins env vars so the root `.env` cannot leak in. Don't
add `pytest-asyncio` unless something genuinely needs it.

## Test and lint entry points

Docker-only, no host toolchain, works with the stack down:

```bash
make test | make backend-test | make frontend-test
make lint | make backend-lint | make frontend-lint | make frontend-typecheck
```

Run `make build` after dependency changes so the CLI images stay fresh.
