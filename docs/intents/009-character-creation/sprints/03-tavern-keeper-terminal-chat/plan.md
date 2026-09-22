---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 03

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | The creation agent: `character/agent/{state,tools,graph}.py`, prompt `character/prompts/v1/system/creator.md`, and in `character/service.py` `build_creation_agent`, `turn`, `render_sheet`, `render_seed`, `render_greeting` | none of its own beyond an import/smoke check; WI2 owns the six criterion tests | – |
| 2 | backend-python | `app character create --run --user` terminal loop in `character/commands.py`, README update, `backend/tests/character/test_creation_agent.py` with six scripted-model scenarios | AC1 greeting names Rosalind and "take Rosalind" saves the seed hero · AC2 race and class set only after a yes, missing one → suggestions · AC3 printed HP/AC equal `build_sheet` for the same inputs · AC4 review shown before save, unconfirmed save writes nothing · AC5 quit → no write · AC6 "Tavern Keeper" only in the prompt file, no identifier carries it | I1 (codes against it, runs tests once WI1 lands) |

No qa work item (backlog: black-box tests only in sprint 05).

## Interfaces
- I1: everything under `research.md → Interfaces` verbatim — `CreationContext`, `CreationState`, the six tools and their model-facing signatures, `build_creation_agent`, `turn` → `CreationTurn(reply, saved)`, the three render functions, prompt id `character/system/creator`, draft-to-request defaults, `save_character` as the only write. Technical decisions 1–8 of the research are binding.
- I2: CLI contract — `app character create --run <id> --user <id>`; one session at startup (run → campaign → seed), one per turn as `app game play` does; `quit`/`exit`/empty line ends with nothing kept; on `saved` print the in-voice finality line and exit 0.

## Order
Parallel: WI1, WI2 (WI2 waits for WI1's commit before running its tests). Then gates.
