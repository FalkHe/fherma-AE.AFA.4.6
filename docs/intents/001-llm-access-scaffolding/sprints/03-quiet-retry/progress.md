---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: draft
---
# Progress: Sprint 03

| WI | Status | Note |
|---|---|---|
| 1 | done | 2 settings + .env.dist, 3 tests, suite 265 |
| 2 | done | Retry-After recovered, config error non-retryable, 16 tests |
| 3 | done | retry.py + seam wiring + structlog isolation fix, commit 401e044 |
| qa | done | AC1-AC5 green; sharpened the sprint-02 socket test |

Status: `open | running | done | failed`

## Issues
- Research came in at 102 lines; sprint lead trimmed two lines of attribution rather than round-tripping the agent.
- **`.env.dist` gains two variables — the human must re-copy them into their `.env`.** `.env.dist` is owner-only, but the human already authorised an edit to it once this intent (D4's `IMAGE_MODEL`).

- Latent test-isolation bug found and fixed: `tests/core/test_error_envelope.py` called `configure_logging()` without `structlog.reset_defaults()`, binding the logger factory to a `capsys` stderr pytest later closes. Inert until sprint 03 logged on the failure path, then it swallowed the CLI's error line entirely. Autouse guards now reset structlog and neutralise `_sleep` across `tests/core/llm/`.
- Sprint 02's socket test asserted one request per trigger; D6's retry makes three. qa split it into a non-retryable 401 case (exactly 1) and a retryable 429 case (exactly `llm_retry_attempts`) — sharper than before.
- WI3 and qa each hit their turn limits once; both resumed with a precise failure list rather than re-exploring.

## Backlog proposals

## Verify
