---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 02

| WI | Status | Note |
|---|---|---|
| 1 | done | builder + schemas, 3 tests; resolve_equipment takes scores too |
| 2 | done | save + attack lookup + route body + client; 1071 unit, 154 db; two stale state-key tests updated |

Status: `open | running | done | failed`

## Issues
- `CharacterSheet` stays in the character module (sprint 01) instead of moving to playthrough as the brief assumed; imports are acyclic, nothing gained by moving it.
- Class defaults that read "any simple/martial weapon" resolve to mace / longsword so every default is a real item; sprint 04 may offer a named pick.
- glab is signed in as f4lkh3; human instruction for this run: merge on my own when the sprint went without bigger issues, rebase from main before starting and before each merge.

## Backlog proposals
- Quantity items (20 arrows) are saved as 20 carried rows; fine today, an inventory screen would want one row with a count.
- `builder.modifier` reaches into the dice module's private helper (noqa); a public `ability_modifier` in dice.py would clean it up.

## Verify
Round 1: approve, no failed criteria. MR description was empty (body extraction bug) and assignee was the agent; both fixed on !54 and !56 before merge.
