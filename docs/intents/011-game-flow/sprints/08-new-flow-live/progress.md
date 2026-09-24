---
author: sprint
owner: agent
created: 2026-09-24
updated: 2026-09-24
stage: done
---
# Progress: Sprint 08

| WI | Status | Note |
|---|---|---|
| 1 | done | five-node graph composed, initial_state, topology test; old service call site pending WI2 |
| 2 | done | run_turn, thread_state, CLI on the new flow; four old test files deleted, run_turn tests added |
| 3 | done | four database scenarios pass; fixed flow gaps found on the way (decision/execute reconciliation, roll kinds, hit attribution, choice payload key, usage shape) |

Status: `open | running | done | failed`

## Issues
- No Dungeon Master tone value exists anywhere in the backend, so the sprint 06 proposal to wire it into narration is not a one-liner and stays out; the requirement-map claim needs a decision (proposal stands).
- No qa agent, per owner's "reduce testing"; AC1 is checked live in the browser by the sprint lead.

## Issues (gates and live check)
- Gates green: lint, 1243 unit, 188 database tests. No wire-schema drift.
- Live on the hosted app: conversation and search turns run on the new flow with the composer, transcript and awaiting behaving as before. A move north narrated a walk but used no exit; the hero stayed on the village green. Fixed: the read-move decision was never told which operation kinds it may propose, so it invented names that failed validation and fell back to narration; now movement records the exit use and the hero changes scene live.
- Live: a search in Thornway narrated without a roll because authored checks were never assessed by the scheduler; now the assess-move step requests the authored roll and the dice chip renders wisdom (Perception) DC 5 with the result. The checkpoint serializer also missed the flow's enum types, which a real Postgres resume silently dropped; fixed.
- Live: an attack in the lair narrated only the attempt and closed the turn with no target choice, initiative or attack roll. Fixed: the attack intent was matched against one literal word, so real phrasing fell through to a plain answer; live now the target binds, initiative is requested and settled, hits reach damage, and a downed hero ends the run in defeat.
- Live: a run from the old flow with the hero already at zero hit points was correctly finished in defeat on the next action, but the closing narration still described the fallen hero attacking. Fixed: the terminal turn owes one closing beat carrying the recorded ending; verified live.
- Final gates green: lint, 1256 unit, 188 database tests; no API client drift.
- Live logs showed checkpoint deserialization warnings for the new state types; the serializer now registers them and tests run in strict mode.

## Backlog proposals
- The verifier repeatedly found live gaps the scripted scenarios did not: consider one database-marked test that drives the real turn endpoint through a pause and resume with the exact values the frontend sends (now added for rolls; add the choice path too).

## Verify
Round 1: changes-requested — AC1/Outcome: a model-proposed operation missing a required payload key raised inside execute (500, run stuck); runs whose pending roll request predates the new flow refuse the roll (409).
Round 2: changes-requested — AC1/AC2: the roll button resumed the pause with an empty value, which the graph library treats as resuming nothing; the two round-1 defects are fixed.
After round 2: the roll resume value fixed and live-verified by the implementer; no third verifier round per process, merge request left as draft.
