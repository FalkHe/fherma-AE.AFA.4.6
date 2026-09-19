---
author: sprint
owner: agent
created: 2026-09-19
---
# Plan: Sprint 05b

`research.md` was written before 05a landed. Its facts about the transcript are now code — read `service.py`,
`schemas.py` and `routes.py` as they stand, and treat the research as the contract, not as a description.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | What a game has cost, whole and turn by turn, exact to the last digit, for its owner alone — reachable only as a command, never as an address | AC3: the sums; a stranger refused; no route anywhere exposes cost | – |
| 2 | backend-python | A live signal that says only "there is something new", and stops when the listener goes away or its time is up | AC4: the content type, the message, the keepalive, the end on disconnect and on the lifetime bound; member-gated before the stream opens | WI1, I1–I3 |
| 3 | backend-python | The module docs record the cost report and the signal, including why cost has no address | AC3, AC4 | I1–I3 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I3 |

## Interfaces
- I1 `run_cost(db, *, user_id, run_id) -> RunCost`, `_require_member` first. `RunCost(total: Decimal, turns: list[TurnCost])`, `TurnCost(turn_id: str | None, total: Decimal)` — plain models, never a wire schema, never a route. Turns grouped by `turn_id`, the `NULL` turn last, empty sums normalised to `Decimal("0.000000")`.
- I2 `app playthrough cost <RUN_ID> --user <USER_ID>`, both required, exit 0, printing:

  ```
  run: <run-id>
  total: 0.001234
  turn <turn-id>: 0.000500
  turn -: 0.000734
  ```

  A `PlaythroughError` prints `f"{exc.code}: {exc}"` on stderr and exits 1, so a foreign run prints `NOT_FOUND`.
- I3 `GET /api/v1/playthrough/campaign/{run_id}/stream`, `CurrentAuth`. Membership is checked **before** the `StreamingResponse` is returned, so a refusal is still an envelope rather than a stream that opens and dies. `media_type="text/event-stream"`, headers `cache-control: no-cache` and `x-accel-buffering: no`. Per tick: `data: {"type":"updated","id":"<ulid>"}\n\n` when `latest_event_id(db, *, user_id, run_id) -> str | None` differs from the last sent, otherwise `: keepalive\n\n`. Settings `sse_poll_interval_seconds: float = Field(default=2.0, gt=0)` and `sse_max_lifetime_seconds: float = Field(default=300.0, gt=0)`, read through `get_settings()` **inside** the handler so a test can pin them. The loop ends on `await request.is_disconnected()`, on elapsed lifetime, or on `GeneratorExit`, and rolls back per poll so an open stream never sits idle in a transaction. The signal carries no content: the client refetches the transcript (← D10).

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_cost_and_live_signal.py`; the cost sums `@pytest.mark.database`.
- AC3 → the command prints the exact totals for the owner, refuses a stranger, and no address exposes cost.
- AC4 → the stream announces a new entry, keeps alive otherwise, and ends both on disconnect and on its time limit.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
WI1 and WI2 both extend `service.py`, so they never run at the same time.

## Note
`TestClient` buffers the response and never delivers a disconnect, so the disconnect path is proven by driving the
generator directly, and the lifetime path through `client.stream` with both settings pinned tiny.
