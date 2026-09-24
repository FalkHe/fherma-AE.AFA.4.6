---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Sprint 04: One trustworthy picture of the moment, and long memory

## Task
Add a single read that returns the run, adventure, scene, actors with their derived roles, health and downed state, attitudes, attacks, inventory, fixtures, exits, conditions, authored facts and consequences, and a bounded window of recent transcript, split into a private view for decisions and a public view for narration. Extend history recall so a semantic match on older narration also returns the surrounding player-visible events of that turn.

## Outcome
One call returns everything a decision needs for a rich scene, and its public half contains no hidden fact and no difficulty number.

## Acceptance criteria
- AC1: Given the goblin lair scene, when the situation is read, then it contains actors with roles, attacks, fixtures, exits, inventory and hidden facts.
- AC2: Given the public view, then no hidden fact, difficulty or private intent appears in it.
- AC3: Given a question about an event older than the recent window, when history is recalled, then the matching narration and that turn's player-visible events are returned.
- AC4: Given missing or broken content, then the read fails loudly instead of returning a partial picture.

## Decisions
← intent §2.1–§2.6

## Assumptions
- Conditions and consequences are the authored exit condition and fixture outcome prose; no new content fields.
- The recent window size is fixed in code.

## Out of scope
Caching the picture or storing it in the checkpoint.
