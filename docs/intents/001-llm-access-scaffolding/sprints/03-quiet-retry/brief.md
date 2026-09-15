---
author: intake
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 03: transient failures are retried before anyone is told

## Outcome
A retryable failure is retried with backoff — each attempt visible in the log —
and the failure line appears only once the attempts are spent.

## Acceptance criteria
- AC1: a gateway stub that fails twice then succeeds makes the command succeed, with no failure line and no non-zero exit.
- AC2: a stub that always fails produces the generic failure line exactly once, after the configured number of attempts, and exits non-zero.
- AC3: a non-retryable class (`LLM_AUTH`) is attempted exactly once — never retried.
- AC4: every attempt is logged with its attempt number and the failure class it is retrying.
- AC5: the suite asserts all of this without sleeping — backoff delays are injectable and zeroed in tests.
- AC6: attempt count and backoff base are settings with documented defaults in `.env.dist`.

## Decisions
← D6, D2

## Assumptions
- `LLM_MALFORMED` is retried once; the other retryable classes use the full attempt budget.
- Backoff is exponential with jitter; a `Retry-After` header on a 429 wins over the computed delay.
- Retry lives in the seam, so every call kind inherits it.

## Out of scope
Showing the player a retry in progress (phase 9) · per-run retry overrides (phase 10) · resuming a failed *turn* (phase 8).
