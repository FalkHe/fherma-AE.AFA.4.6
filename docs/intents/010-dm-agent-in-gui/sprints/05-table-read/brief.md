---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Sprint 05: The play screen's own read: adventure, scene and party

## Task
Add the read a play screen opens with: the current adventure's title, the current scene's name, and each seated member's hero with name, race, class, level, current and maximum hit points, armour class, ability scores with modifiers, appearance, backstory and carried items. One read serves the header, the party rail and the full sheet alike.

## Outcome
Reading a run under way from the interactive API page returns its adventure title, its scene name, and the ready-made hero with hit points, armour class and ability scores in one answer.

## Acceptance criteria
- AC1: Given a run under way, when the table is read, then it names the current adventure and the scene the hero stands in.
- AC2: Given the same run, when the table is read, then each seated hero carries name, race, class, level, current and maximum hit points, armour class, six ability scores with modifiers, appearance, backstory and items.
- AC3: Given a turn that wounded the hero, when the table is read again, then the current hit points reflect it.
- AC4: Given a run the caller is not seated at, when read, then it is refused.

## Decisions
← D7, D12, D15

## Assumptions
- Level is always 1 today; nothing stores another.
- The current scene is the acting hero's scene.
- Created characters from intent 009 flow through the same read once they exist; 009's character card should reuse it rather than add a second.

## Out of scope
Anything on screen · initiative and conditions (← D7).
