---
author: fhit:architect
owner: human
created: 2026-09-17
stage: approved
---
# Sprint 02: the schema accepts the lifecycle this phase writes

## Task
Check the landed database schema and model (`playthrough/models.py`, migrations `0003`–`0006`) against the new mechanics and lifecycle, and correct or enhance both in one additive migration `0007`: the run status set the lifecycle writes, a template-less generated character, the twelve event types, and the `temperature` type mismatch. Rewrite the 003 tests and docs that pinned the old values.

## Outcome
On a fresh database a campaign run inserts with no status and comes out `setup`, all five of `setup ready active
archived finished` are accepted and `paused` is refused, a creature with no `template_id` inserts, all twelve event types
are accepted and a thirteenth is refused, and `downgrade -1` restores the `0006` schema exactly.

## Acceptance criteria
*Each AC is a `@pytest.mark.database` test over `playthrough_db`: green under `make backend-test-db`, skipped under `make backend-test`.*
- AC1: `campaign_runs.status` CHECK is `('setup','ready','active','archived','finished')` with `server_default 'setup'`; the two 003 tests asserting `active` as default and the three-value set are rewritten, not deleted.
- AC2: `objects.template_id` is nullable; a creature row with `template_id NULL` and `member_id` set inserts; `stats_creature_only` and `hp_range` are untouched.
- AC3: `events.type` CHECK is the twelve values of D9; each inserts, `'foo'` raises.
- AC4: `alembic downgrade 0006` restores the three original CHECKs and `NOT NULL`; `CampaignRun.temperature` is `Mapped[Decimal]`; `playthrough/README.md` and `docs/modules/playthrough.md` §3/§7 name the new sets; `make lint`, `make backend-test`, `make backend-test-db` pass.

## Decisions
← D3, D4, D9 · research §A1–A4

## Assumptions
- Bare constraint names (`status`, `type`) are dropped and recreated under the same names — renaming would touch `0003`/`0006`.
- `template_id` goes nullable rather than carrying a `seed-player-character` sentinel (research §A2).
- A4 rides along: no migration, same `models.py`, must precede sprint 03's first write.

## Out of scope
No service, route or schema module · no new table or column — three CHECKs and one nullability · `events.turn_id` stays a bare column (← research §C3).
