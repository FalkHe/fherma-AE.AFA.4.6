---
name: qa-checklist
description: Conventions and known traps to check when changing this repo — generated API types drifting, the openapi-typescript/TypeScript peer pin, the unsubsetted icon font, and the lru_cache'd async engine vs pytest event loops. Use when reviewing or landing backend/frontend changes, adding tests, or touching FastAPI routes and response models.
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
for a payload the backend does not send yet. `useCatalogueModel.ts` carries one
for `usedPrice` — delete it when the backend field lands, don't build on it.

## Watch the openapi-typescript / TypeScript peer pin

`frontend/package.json` pins `typescript@6.0.3`, while the installed
`openapi-typescript@7.13.0` declares a peer dependency of `typescript: ^5.x`.
This works today (pnpm does not hard-fail on the mismatch), but re-verify when
either package is bumped: a later `openapi-typescript` may tighten the range, or
TypeScript 6.x may break something 7.13.0 was never tested against.

## Material Symbols is loaded unsubsetted

`frontend/src/main.tsx` imports `material-symbols/outlined.css`, which pulls the
full outlined glyph set as a single ~3.8 MB `.woff2`.

This is an **accepted cost**, not a bug to fix on sight: icons are used as
`<Icon>` ligatures and `@mui/icons-material` is deliberately not a dependency.
If the payload ever matters, subset the font to the glyphs actually used —
switching icon libraries would touch every component.

## `lru_cache`'d async engine — pytest event-loop trap

`backend/app/db/session.py` caches the async engine and session factory with
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

## Worker does not hot-reload

`app-worker` runs without `--reload`. After changing ORM models, services or
task code, `docker compose restart app-worker` — otherwise you are testing the
old code path and will misread the result.

## Test and lint entry points

Docker-only, no host toolchain, works with the stack down:

```bash
make test | make backend-test | make frontend-test
make lint | make backend-lint | make frontend-lint | make frontend-typecheck
```

Run `make build` after dependency changes so the CLI images stay fresh.
