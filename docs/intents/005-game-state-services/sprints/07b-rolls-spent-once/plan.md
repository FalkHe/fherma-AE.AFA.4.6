---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 07b

`research.md` covers both halves of split sprint 07; 07a is merged. In scope: the two consumers, single
consumption, and `awaiting` on the events read.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A roll turned into pass or fail, and spent exactly once — not twice, not in a later turn, not for another kind of thing | AC3: pass and fail on the spending entry; each refusal raised *and* recorded for the DM only; a refused attempt does not burn the roll | – |
| 2 | backend-python | The transcript read also says what the game is waiting for, if anything | AC4b: `none`, a roll or an answer, from the open turn; the read's new shape | WI1, I1–I4 |
| 3 | backend-python | The module docs describe spending a roll, its refusals, and what the client is told it awaits | AC3, AC4b | I1–I4 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I4 |

## Interfaces
- I1 `resolve_check(user_id, roll_id, dc) -> bool` and `resolve_save(user_id, roll_id, dc) -> bool`, both `async`, `db` first, rest keyword-only, both taking `turn_id: str | None = None`. Each appends `tool_call {name, args{rollId, dc}, rollIds:[roll_id], result:"ok", outcome{total, dc, success}}` at `dm` — pass or fail lives on the mechanic that spent the roll, never on the roll itself (← D11).
- I2 `_consume_roll(run_id, roll_id, kind, turn_id)` decides from the transcript alone, with no consumption column: the entry exists, is a `roll`, and belongs to this game · its `kind` matches, so a `custom` roll fails every check · its turn equals the consuming call's, both untagged counting as equal · **no** `tool_call` in that same game-and-turn with `result: "ok"` already names this roll in `rollIds`. A *refused* attempt must not burn the roll.
- I3 Refusals, each recorded as a `tool_call` with `result: "refused"` at `dm` and **committed before the error is raised** — `append_event` only flushes, and the caller's rollback would erase the record (the pattern `use_exit` established). New codes, both 409: `ROLL_NOT_USABLE` for a roll already spent, from another turn, or of another kind; `INVALID_DC` for a difficulty outside 5–30. An unknown roll id stays `NOT_FOUND`.
- I4 `get_awaiting(user_id, run_id) -> "none" | "roll:<id>" | "answer:<id>"`, derived from the open turn's entries — no stored cursor (← D9). `GET …/campaign/{run_id}/events` answers `EventsRead {events: [...], awaiting}` instead of a bare array. Nothing outside the backend reads it yet, so the blast radius is two existing tests; `frontend/src/api/schema.d.ts` is **not** regenerated (phase 9 owns that).

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_rolls_spent_once.py`; database-touching tests carry `@pytest.mark.database`.
- AC3 → a roll becomes pass or fail on the spending entry; twice, a later turn, another kind, or a difficulty outside 5–30 are each refused and recorded; a refusal leaves the roll spendable; a custom roll is refused by both.
- AC4b → the read says nothing is awaited, or names the roll or question awaited.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
WI1 and WI2 both extend `service.py`, so they never run at the same time.

## Note
The README cites `playthrough/cli.py` for the roll command, which lives in `commands.py` — a slip already on
`main`; WI3 fixes it in passing.
