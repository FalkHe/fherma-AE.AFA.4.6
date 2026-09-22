---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 11: The party rail, with hit points that move

## Task
Add the party rail of D12 — name, race, class, level, hit points and armour class per hero — refreshed on the same tick as the transcript, and its narrow-screen form: a one-line strip pinned under the header that opens into the card on tap. No initiative and no conditions.

## Outcome
A turn that wounds the hero lowers the hit points on the rail within a couple of seconds of the roll landing, and on a narrow screen the strip keeps them in sight while the transcript scrolls.

## Acceptance criteria
- AC1: Given the play screen, when it loads, then the rail shows "Party" and each hero as D12's card: name, "{race} {class} · Level {n}", "HP {current} / {max}", "AC {n}".
- AC2: Given a turn that changes hit points, when the roll lands, then the rail's number changes within a few seconds without a reload.
- AC3: Given a narrow screen, when rendered, then the strip "{name} · HP x/y · AC z" is pinned under the header and opens into the card on tap.
- AC4: No initiative, no conditions on the card.

## Decisions
← D7, D12

## Assumptions
- The rail refreshes with the transcript, so hit points land about two seconds after the roll.
- One hero exists today; the rail is a list anyway.

## Out of scope
The full sheet (12) · conditions and initiative (← D7).
