---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 02

Two reads and the two commands that show them, in parallel against one shared result shape. Last sprint of the
intent; it stacks on sprint 01's branch, which is shipped but not merged.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Asking a run a question returns the lines of narration closest to it in meaning, from anywhere in the run, never one that failed to be encoded | AC1, AC3: the closest line first against a real database; a line from an earlier adventure of the same run when it is the closest; a line with nothing encoded never returned; no relevance floor, one encoding call | I1, I2 |
| 2 | backend-python | Asking a run for a recap returns its newest narration, oldest first, with no question asked | AC2, AC4: the newest chosen, returned in reading order, no encoding call; a run with no narration returns nothing | I1, I2 |
| 3 | backend-python | Both reads are usable from the command line, one line per remembered entry | AC5: each prints id, time and text per line; a run that does not exist prints a message and exits non-zero | I3 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I3 |

## Interfaces
- **I1 — the result shape** (`playthrough/schemas.py`, owned by WI2, imported by WI1): `class NarrationRead(CamelModel)` with `id: str`, `created_at: datetime`, `text: str` — those three fields, that order, for both reads. No distance, no payload, no vector. `EventRead` is not reused: it is the transcript route's wire model and carries `type`/`turnId`/`payload`.
- **I2 — the two reads** (`playthrough/service.py`, after `latest_event_id`). Neither takes `user_id` — operator reads, gated on existence alone — and both call `await _get_run(db, run_id)` as their **first** statement, so an unknown run raises the module's existing not-found error rather than each caller inventing a check.
  - `async def recall(db: AsyncSession, *, run_id: str, query: str, k: int = 5) -> list[NarrationRead]`: one embedding call, `result = await asyncio.to_thread(llm_service.embed_texts, [query])` (module attribute, never a name import), `vector = result.vectors[0]`; seam errors propagate unchanged — D4 covers writes, and showing an operator "no memories" when the encoder is down would be worse. Statement: `select(Event.id, Event.created_at, Event.payload).where(Event.campaign_run_id == run_id, Event.type == "narration", Event.embedding.is_not(None)).order_by(Event.embedding.cosine_distance(vector)).limit(k)` — predicates matching sprint 01's partial index verbatim, and `Event` itself never selected, so no 1536-float vector crosses the wire. Closest first, no relevance floor.
  - `async def recap(db: AsyncSession, *, run_id: str, n: int = 5) -> list[NarrationRead]`: **no** embedding call. Same columns and mapping; `.where(Event.campaign_run_id == run_id, Event.type == "narration").order_by(Event.id.desc()).limit(n)`, then `list(reversed(rows))` — the newest `n` chosen in SQL, oldest first on return. No vector filter: recency does not care. This shape is what makes AC4 provable without a database, since the stubbed session never parses SQL.
  - Both return `[]` when the run has no narration; neither commits nor rolls back.
- **I3 — the commands** (`playthrough/commands.py`, after `narrate`), no `--user`: `app playthrough recall RUN_ID QUERY [--k INTEGER]` and `app playthrough recap RUN_ID [--n INTEGER]`, both defaulting to 5. Each opens its session as `narrate` does and prints one line per item and nothing else: `f"{item.id} {item.created_at.isoformat()} {item.text}"`. An empty result prints nothing and exits 0. `PlaythroughError` → `f"{exc.code}: {exc}"` on stderr plus exit 1, so an unknown run prints `NOT_FOUND: campaign run not found: {RUN_ID}`.

`backend/tests/playthrough/conftest.py` gains the pin `EMBEDDING_DIMENSIONS="1536"` (WI1), rather than a second fixture.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_recall_and_recap.py`.
- AC1, AC3 → `@pytest.mark.database` over a run with narration in two adventures, the encoder monkeypatched to fixed 1536-wide vectors: the closest line first, the earlier adventure's line returned when it is the closest, an unencoded line never returned.
- AC2, AC4 → the newest lines, oldest first, and no encoding call made.
- AC5 → both commands print id, time and text per line; an unknown run exits non-zero with a message.

## Order
Parallel: WI1, WI2, WI3, qa.
