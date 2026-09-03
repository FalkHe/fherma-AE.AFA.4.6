# QA checklist

Conventions to check before/after a change, and known rough edges to keep in
mind while extending Phase 0's foundations. Not enforced by CI yet.

## Generated API types must never drift

The frontend's typed client (`frontend/src/api/schema.d.ts`) is generated
from the backend's OpenAPI schema and committed to git. After any change to
a FastAPI route, request/response model, or anything else that affects
`app.openapi()`:

```bash
make generate-api    # or, with host pnpm: cd frontend && pnpm generate:api
git diff --exit-code frontend/src/api/schema.d.ts
```

- `make generate-api` requires the stack running (`make up`) — it exports the
  schema from the `app-web` container, then runs `openapi-typescript` in a
  one-off `node-cli` container (no host Node needed).
- If `git diff --exit-code` reports a diff, the committed types were stale;
  commit the regenerated file.
- If it reports no diff, the schema didn't actually change (or was already
  regenerated) — nothing to do.

## Watch the openapi-typescript / TypeScript peer-dependency pin

`frontend/package.json` pins `typescript@6.0.3`, but the installed
`openapi-typescript@7.13.0` declares a peer dependency of `typescript: ^5.x`.
This works today (pnpm does not hard-fail on the mismatch), but re-verify
compatibility any time either package is bumped — a future `openapi-typescript`
release may tighten the peer range, or TypeScript 6.x may introduce a break
that 7.13.0 wasn't tested against.

## Material Symbols font is unsubsetted

`frontend/src/main.tsx` imports `material-symbols/outlined.css`, which loads
the full outlined glyph set as a single ~3.8 MB `.woff2`. Fine for Phase 0's
single icon or two; before the UI grows in Phase 1, either subset the font to
the glyphs actually used or switch to `@mui/icons-material` (per-icon tree
shaking).

## `lru_cache`'d async engine — pytest event-loop pitfall

`backend/app/db/session.py` caches the async engine and session factory with
`@lru_cache`, keyed process-wide (not per event loop). This is correct for
the running app (one event loop for the process lifetime) but will break
async pytest fixtures: if a test runner creates a new event loop per test (or
per module), reusing the cached engine from a previous loop raises errors
like "Future attached to a different loop" or silently hangs.

When adding pytest fixtures for code that touches the database, either:
- call `get_engine.cache_clear()` and `get_sessionmaker.cache_clear()` in a
  fixture teardown/setup between tests that get a fresh event loop, or
- construct a dedicated engine/sessionmaker in the test fixture instead of
  going through `get_engine()`/`get_sessionmaker()`.

The current suite (`backend/tests/`) sidesteps this entirely: it is fully
synchronous and stubs the DB session via a `get_db_session` dependency
override, so no real engine is ever constructed. The note above applies the
moment someone adds an async fixture that touches `get_engine()`/
`get_sessionmaker()`.
