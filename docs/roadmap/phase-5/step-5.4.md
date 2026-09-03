---
phase: 5
step: "5.4"
title: Global 500 catch-all handler
summary: Register one Exception handler in main.py returning a generic JSON:API ErrorDocument (code internal-error) with no exception details; traceback goes to the server log only. Everything else in the pinned error-shape split is untouched.
effort: 1
dependencies: []
---

# Step 5.4 — Global 500 catch-all handler

**Effort: 1** — one handler, one test file, against a fully pinned contract
(shared-knowledge D1).

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (read fully —
D1 is the wire truth). Prior pins: the error-shape split in
`docs/roadmap/phase-2/shared-knowledge.md` (~lines 693–702) and the JSON:API
layer as landed (`backend/app/api/jsonapi.py`). Agent: **backend-dev**. Zero
deviations — a deviation is a stop-and-report.

**Environment:** compose stack state does not matter (TestClient-only), but
the pre-dispatch CORS chore commit on `backend/app/main.py` must have landed
first (open-questions A1) — verify `git status` is clean before starting.

## Outline

- `backend/app/main.py`: register a handler for bare `Exception` **beside**
  the existing `JsonApiError` handler (do **not** create `api/errors.py` —
  the Phase-2 one-handler-in-main.py pin). Body: the existing
  `jsonapi.error_document(500, "internal-error", <generic sentence>)`;
  `logger.exception(...)` before returning. Nothing from the exception
  (type, message, args) may reach the response in any environment.
- Do not touch: the `RequestValidationError` default (FastAPI 422 `detail`
  shape stays), auth/CSRF dependency bodies, any existing JSON:API error
  code, CORS/middleware ordering.
- Tests in `backend/tests/api/` (new file): a route monkeypatched to raise →
  `TestClient(app, raise_server_exceptions=False)` sees status 500, the
  envelope `{"errors":[{"status":"500","code":"internal-error","detail":…}]}`,
  and the detail contains no exception text; a second test proves existing
  shapes unchanged (e.g. a 422 keeps the `detail` list shape).

## Verification

- `make backend-test` + `make backend-lint` green (suite currently 1213).
- Live curl: force an error (e.g. temporarily raising route via a scratch
  patch, or an existing deterministic 500 path if one exists) → envelope,
  no traceback; normal routes unaffected.

## Risks / notes

- Starlette's `ServerErrorMiddleware` wraps handlers registered for
  `Exception` via `add_exception_handler` — confirm the handler actually
  fires under TestClient with `raise_server_exceptions=False` and under
  uvicorn, not just in unit isolation.
- Append cross-step decisions (`### Step 5.4`) to `shared-knowledge.md` —
  5.17's forced-500 check proves this contract.
