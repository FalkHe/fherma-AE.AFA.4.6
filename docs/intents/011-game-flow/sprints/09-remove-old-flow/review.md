---
author: sprint
owner: agent
created: 2026-09-26
updated: 2026-09-26
url:
---
# Review: Sprint 09 — The old game flow is gone

## What changed
The replaced game machinery is deleted: the old tool collection, the guard step, the combat-specific steps, the message-based state, the old system prompt, the generated graph diagram and every test that asserted them. The game module README, the architecture documents, the glossary, the data model, the requirement map and the documentation index now describe only the five-part flow with its two read-only aids, rules lookup and history recall. The play works exactly as it did after sprint 08; nothing a player sees changes.

## How to check it
- Search the backend and current docs for the old names (for example `DmContext`, `load_context`, `dm.md`): nothing matches.
- Open `docs/architecture.md` and `backend/app/modules/game/README.md`: both describe the five-part flow and the two aids, and no document under `docs/general/` links to a missing file.
- Run `make lint` and `make test`: both green.

## Heads-up
The opt-in database test suite (`make backend-test-db`) fails 22 of its 189 tests with missing item rows; the same failures reproduce on `main`, so they predate this sprint and are proposed as a fix-up in the backlog. The regex prompt-injection guard leaves with the old flow, as intent 011 planned; "security guard" in the requirement map now rests on ownership and authentication boundaries.

Brief: docs/intents/011-game-flow/sprints/09-remove-old-flow/brief.md

## Verdict
