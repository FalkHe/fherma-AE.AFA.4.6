---
author: fhit:architect
owner: human
created: 2026-09-23
updated: 2026-09-23
stage: approved
---
# Backlog

01–05 are checked in the terminal or API page, 06–13 in the browser.

| # | Task | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | The terminal game knows which hero acts, resumes a run where it was left, and marks it under way | – | #55 | done |
| 02 | Each turn's cost is recorded; a momentary model failure is retried quietly, not fatal | 01 | #56 | done |
| 03 | An action, answer, roll, retry or the opening of a new adventure can be sent to the game over the network | 01 | #57 | done |
| 04 | Rule lookups and changes in the world become short lines the player can see | 01 | #58 | done |
| 05 | One read gives the play screen its adventure, scene and each hero's hit points, armour class and sheet | 01 | #59 | done |
| 06 | "Continue" opens play on its own screen with everything recorded so far; back returns to the lobby | 04, 05 | #60 | done |
| 07 | The player writes what they do, watches the Dungeon Master think as dice and questions appear, then reads the narration | 03, 06 | #61 | done |
| 08 | "Start adventure" opens a new adventure straight into play, where the Dungeon Master writes the opening scene | 03, 07 | #62 | done |
| 09 | When the Dungeon Master asks or calls for a roll, only the offered buttons work; the game rolls | 07 | #63 | done |
| 10 | A long turn says so and waits; a broken one ends in-voice with "Try again", nothing already rolled lost | 07 | #64 | open |
| 11 | Beside the transcript each hero shows hit points and armour class, changing as rolls land | 05, 07 | #65 | open |
| 12 | Tapping a hero opens the full sheet over the transcript; closing it returns to play | 11 | #66 | open |
| 13 | An adventure's ending is narrated and marked, one button leads back to the lobby, which files it as done | 06, 08 | #67 | open |

## Notes

- 02 and 03 run in sequence; 04, 05 beside them; 09–11 side by side after 07. Acceptance tests for 03 only.
- Coverage: D1→06,08 · D2→07,09 · D3→07 · D4→10 · D5→02,10 · D6→01,06,09,10 · D7→05,11 · D8→02 · D9→01,08 ·
  D10→04 · D11→13 · D12→06,11,13 · D13→03,08 · D14→06 · D15→05,12.
- Not sprints: cost, model or tone on screen (← D8) · scene artwork (← D14) · replaying a finished adventure (← D11).

## Proposals

- A check's difficulty and whether the roll made it are never written where a player can read them, so the dice chip cannot show D12's verdict; recording them is its own row.

- The host's proxy may cut a request before D5's two minutes; 03 measures it and reports.
- 009's sprint 07 (character card on the lobby) should reuse 05's read and 12's sheet.
- A finished campaign has nothing left on the lobby; no decision covers it.
