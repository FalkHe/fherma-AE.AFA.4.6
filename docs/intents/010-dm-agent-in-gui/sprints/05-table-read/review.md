---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
url: –
---
# Review: Sprint 05 — The play screen's own read

## What changed
One read now answers everything a play screen opens with: the run and its campaign, the adventure under
way, the scene the hero stands in, and every seated hero's full sheet — name, race, class, level, current
and maximum hit points, armour class, the six ability scores with their modifiers, appearance, backstory
and carried items. The same answer serves the screen's header, the party rail beside the transcript and
the full sheet alike, so there is one hero shape rather than three.

## How to check it
- Read a run under way from the interactive API page: it names the current adventure and the scene the
  hero stands in (AC1).
- The same answer carries the ready-made hero with all of the above, modifiers included (AC2).
- Wound the hero in a turn and read again: the current hit points have fallen (AC3).
- Read a run you are not seated at: refused (AC4).

## Heads-up
The adventure shown is the one the hero is actually standing in, not whichever the run last marked active
— otherwise the header would go blank at exactly the moment an adventure ends, which a later sprint still
has to show. Carried items arrive one per unit, so the screen groups identical ones itself. Every read
that already returned a hero gained these fields, so intent 009's character card can drop its own copy
rather than keep a second shape.

Brief: docs/intents/010-dm-agent-in-gui/sprints/05-table-read/brief.md

## Verdict
