---
author: sprint
owner: agent
created: 2026-09-19
---
# Plan: Sprint 05a

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | One way to write to the transcript, refusing any entry whose content does not match what its kind promises | AC1: each of the twelve kinds validated and stored; a wrong shape refused and nothing written; nothing else in the tree writes an event | – |
| 2 | backend-python | The player's transcript read: in order, paged, and without the entries meant for the DM | AC2: ordering by id alone, `after` exclusive, the limit honoured; a DM entry between two player entries absent from the read and present in the table; member-gated | WI1, I1–I3 |
| 3 | backend-python | The module docs record the writer, the read and the caveat that entry ids order the transcript only because one process mints them | AC5 | I1–I3 |
| qa | qa | Black-box acceptance tests, one per criterion | below | I1–I3 |

## Interfaces
- I1 `append_event(db, *, run_id, type, visibility, payload, turn_id=None, actor_member_id=None, usage=None) -> Event` — async; `add` + `flush` so the id exists, **no commit**, the caller owns the transaction. `payload` (a dict or the type's model) is validated through `EVENT_PAYLOADS[type]` and stored `model_dump(by_alias=True)`; an unknown type or visibility, or a payload that fails, raises `InvalidEventPayloadError` (new, `ErrorCode.VALIDATION_ERROR`) and writes nothing. `usage` is `core.llm.service.Usage`: tokens copy across and `cost_usd` becomes `Decimal(str(usage.cost_usd))`, never `Decimal(float)` — 05b needs exact decimals. No membership check; callers are gated.
- I2 Payload models in `playthrough/schemas.py` (`CamelModel`, `extra="forbid"`), registry `EVENT_PAYLOADS: dict[str, type[BaseModel]]` covering all twelve types; names and shapes verbatim in `research.md → Interfaces`. Stored camelCase and passed through the read unmapped.
- I3 `GET /api/v1/playthrough/campaign/{run_id}/events?after=<id>&limit=<n>` → `list[EventRead]`, `CurrentAuth`, `NOT_FOUND` for an unknown or foreign run. `after` optional, exclusive; `limit` `Query(default=200, ge=1, le=500)`. `list_events(db, *, user_id, run_id, after=None, limit=200) -> list[Event]` — `visibility='player'`, `ORDER BY id`. `EventRead` (`CamelModel`): `id, type, turnId, payload, createdAt` — no visibility, no cost, no run id.

## Acceptance tests (qa)
`backend/tests/playthrough/test_acceptance_transcript_writer_and_read.py`; AC2 `@pytest.mark.database`.
- AC1 → every kind of entry is accepted with its own shape; a wrong shape writes nothing.
- AC2 → the read is ordered and pages with `after`, and hides the DM's entries while the table keeps them.
- AC5 → the caveat is stated where a reader of the module doc will meet it.

## Order
Parallel: WI1, WI3, qa. Then: WI2.
