---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 05 — a rules question comes back with passages we can cite

| WI | Status | Note |
|---|---|---|
| 1 | running | |
| 2 | open | |
| 3 | open | |
| qa | running | |

Status: `open | running | done | failed`

## Issues
- Research measured retrieval against the real rulebook before anything was built, and found a defect worth knowing about: a rule could not reliably be found by its own name. Asking what Fire Bolt does ranked the actual spell 47th, behind a fire elemental and a red dragon, because only a passage's body was ever learned and a spell's name lives in its heading — so every spell looked like an interchangeable block of casting time and components. Conditions and combat actions already ranked first. One criterion here requires a spell lookup to work, so this sprint fixes what gets learned and re-imports, at about a cent.
- That fix makes one line of the approved structure note slightly untrue: a passage's stored text is what gets quoted, but no longer exactly what gets learned. The note is the human's to amend.
- Five results by default, the sprint lead's choice.
- Fifth merge request in an unmerged chain.

## Backlog proposals
- Citation trails read oddly where the rules text skips a heading level: a rule can appear nested under a sibling rather than its real parent, as in "Acid Arrow › Fire Bolt". Still accurate enough to cite, but it will look wrong to a player once citations are shown.

## Verify
<pending>
