---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 02: every gateway failure is distinguishable, and says one thing

## Outcome
Every failure the seam can meet surfaces as its own domain code behind one
generic failure line, with the provider's own wording only under `--details`.

## Acceptance criteria
- AC1: eight codes exist and each is raised for its own trigger — `LLM_AUTH` (401) · `LLM_BUDGET` (402) · `LLM_RATE_LIMIT` (429) · `LLM_TIMEOUT` (408 and client-side) · `LLM_REFUSED` (403 or `finish_reason:"content_filter"`) · `LLM_UNAVAILABLE` (502/503 or mid-stream `finish_reason:"error"`) · `LLM_MALFORMED` (structured-output parse failure) · `LLM_BAD_REQUEST` (400).
- AC2: every one of the eight is asserted by a test with **no API key** — a stub gateway raising each status is enough.
- AC3: all eight print the same generic failure line and exit non-zero; the code itself is not in that line.
- AC4: `--details` additionally prints the provider's own message when the response carried one, and says so plainly when it did not.
- AC5: each code carries a retryable flag — rate-limit, timeout, unavailable and malformed are retryable; auth, budget, refused and bad-request are not.
- AC6: the codes reach the HTTP wire through the existing `ErrorCode` / `ApiError` envelope in `backend/app/core/errors.py`.

## Decisions
← D2

## Assumptions
- Context overflow is **not** separable — OpenRouter returns a generic 400, so it folds into `LLM_BAD_REQUEST`.
- Failure injection needs no key: an override base URL plus a bogus model id.

## Out of scope
Retry behaviour (03) · the player-facing wording and the "more" disclosure as UI
(phase 9) · embeddings and images raising these codes (04, 05).
