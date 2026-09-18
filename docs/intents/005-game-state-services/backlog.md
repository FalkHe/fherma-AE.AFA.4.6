---
author: fhit:architect
owner: human
created: 2026-09-17
updated: 2026-09-18
stage: approved
---
# Backlog

Sprints, dependency-ordered; each row is the task, its brief carries the outcome and criteria. Status: `open | running | done`.

**How "verifiable by using the product" reads here.** Phase 5 ships services, the lifecycle routes, the events read and
the SSE signal — not the turn (phase 8) and not a screen (phase 9). So 03–06 are verified over HTTP (`TestClient`,
curl against `make up`), 01 and the cost / roll one-offs through the `app` CLI, and 02, 07, 08, 09 — the mechanics no
route reaches yet — as `@pytest.mark.database` acceptance tests under `make backend-test-db`, 003's own precedent.

| # | Sprint (task) | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | Check content schema + `greenhollow` against the mechanics; add `Exit.id`/`Exit.kind`, item-template seed inventory; fix loader rules and shipped content | – | #21 | failed |
| 02 | Check schema + model against the mechanics; migration `0007` for status set, nullable `template_id`, twelve event types; fix `temperature` type; update 003 tests and docs | – | #22 | open |
| 03 | Build the service/route skeleton and `start_campaign_run` + list; instantiate all objects unpositioned; establish the membership gate | 02 | #23 | open |
| 04 | Implement `create_character` (seed sheet, carried items, `setup → ready`), rename/archive/unarchive, archived read-only; fix `docs/general/model.md` lifecycle rows | 01, 03 | #24 | open |
| 05 | Implement `append_event` + payload models, `GET …/events?after=`, `app playthrough cost`, SSE `GET …/stream` | 02, 03 | #25 | open |
| 06 | Implement `enter_adventure` (placement, `adventure_started`) and `use_exit` (scene move / adventure end / campaign finish) | 01, 04, 05 | #26 | open |
| 07 | Implement `dice.py`, formula derivation, `request_player_roll`/`resolve_roll_request`/`roll`/`passive_check`, `resolve_check`/`resolve_save`, single consumption, `awaiting`, `app playthrough roll` | 05 | #27 | open |
| 08 | Implement `interact`, `take`/`drop`/`give`, the one-action-per-turn count, `use_item` seam | 06, 07 | #28 | open |
| 09 | Implement `attack`, `damage`, `roll_initiative` as events-only combat; prove no combat state exists | 06, 07 | #29 | open |

Outcomes — the one verifiable statement per sprint — live in each `sprints/NN-*/brief.md` (`## Outcome`).

## Notes

- Parallelism: 01 ‖ 02 · 06 ‖ 07 (after 05) · 08 ‖ 09.
- **02 is its own sprint**: migration `0007` serves 03/04 (A1, A2) *and* 05 (A3); folding it into 03 would put one
  sprint on everybody's critical path, and it rewrites two existing 003 tests and two doc sections — one coherent hour.
  A4 (`temperature` → `Decimal`) rides along, same file, before the first writer.
- **01 is its own sprint**: a different module with its own loader rules; B1 is not additive — R10 today is literally
  `scene.exits == []` (`content/service.py:199`), so an ending exit breaks a shipped rule until R9/R10 are restated.
  Two consumers (04 needs B2, 06 needs B1), so neither is the natural home.
- **Rejected as outcomes:** "a turn happens" and "the player clicks to roll" (phase 8, ← D10, D14) · "the service
  rejects an illegal write" (← D1: rejection is the tool layer's; only game rules stay) · one sprint per mechanic
  (`take` without `drop` is half a rule) · a separate SSE sprint (same route module and gate as `GET /events`) · a cost
  route (← D14: no drawer yet) · character generation (phase 7, ← D4) · "combat opens an encounter" (← D7) · a
  `docs/general/` sprint (only `model.md:311`-`312` contradict, folded into 04) · any frontend.
- Coverage: D1 → 03, 04, 06, 07, 08, 09 · D2 → 04, 08, 09 · D3 → 02, 03, 04, 06 · D4 → 02, 04 · D5 → 07 · D6 → 07, 09 ·
  D7 → 08, 09 · D8 → 01, 06 · D9 → 02, 05, 07 · D10 → 05 · D11 → 07, 08, 09 · D12 → 03, 04 · D13 → 07 · D14 → 05.

## Proposals

- **For phase 7 (Character Creation): retire the seed player character cleanly.** The seed (`Campaign.seed_character`,
  content §5.11) is phase-1 scaffolding that exists only so phases 3 and 5 have a creature before the generation agent
  lands. Phase 5 spends on it exactly once (01: inventory becomes item-template ids, rule R20) and feeds it into
  `create_character(db, user_id, run_id, sheet)` as the `sheet`. Phase 7 should: (a) decide whether `seed_character`
  survives as a "quick start" pregenerated character or is removed from the content schema, `greenhollow` and R20 in
  one sprint; (b) generate into the **same** `create_character` signature — the function does not change, only the
  source of the sheet; (c) rename `SeedCharacter` to what it then is (a character sheet) and drop the word "seed" from
  `docs/general/glossary.md`, `docs/modules/content.md` and `docs/modules/playthrough.md`. Nothing here blocks 005.
