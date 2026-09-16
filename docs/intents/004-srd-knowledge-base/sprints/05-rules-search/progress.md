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
| 1 | done | search returns the closest passages best first, refusing an empty rulebook before spending a call; index use confirmed |
| 2 | done | `srd search` prints citation, score and passage, best first, with a cap flag |
| 3 | done | the heading trail is now learned with the passage; stored text still the body alone |
| qa | done | one acceptance test per criterion, AC1-AC6 |

Status: `open | running | done | failed`

## Issues
- Research measured retrieval against the real rulebook before anything was built, and found a defect worth knowing about: a rule could not reliably be found by its own name. Asking what Fire Bolt does ranked the actual spell 47th, behind a fire elemental and a red dragon, because only a passage's body was ever learned and a spell's name lives in its heading — so every spell looked like an interchangeable block of casting time and components. Conditions and combat actions already ranked first. One criterion here requires a spell lookup to work, so this sprint fixes what gets learned and re-imports, at about a cent.
- That fix makes one line of the approved structure note slightly untrue: a passage's stored text is what gets quoted, but no longer exactly what gets learned. The note is the human's to amend.
- Five results by default, the sprint lead's choice.
- Two agents were cut off part-way by a usage limit. The search work survived intact and was checked and committed by the sprint lead; the acceptance tests were resumed. Nothing was lost.
- Fifth merge request in an unmerged chain.

- The report's passage-size figure now counts the heading trail too, which is honest about what is learned but makes one schema comment slightly stale.
- Passages carry the raw HTML tables the source document uses, so a table-heavy rule prints as markup rather than readable text. Harmless for matching, but it will need handling before a player sees a quoted rule.

## Backlog proposals
- Citation trails read oddly where the rules text skips a heading level: a rule can appear nested under a sibling rather than its real parent, as in "Acid Arrow › Fire Bolt". Still accurate enough to cite, but it will look wrong to a player once citations are shown.

## Gates
Lint, both suites and the live-database run all pass (634 offline, 27 live, 53 frontend).

By-eye check against the real rulebook after re-importing (2,132 passages, 529,572 tokens, $0.010591): "how does half cover work" returns Combat > Cover first, "what does the poisoned condition do" returns the Poisoned condition first, "how does grappling work" returns Grappling first, and "what does fire bolt do" now returns Fire Bolt first, where before the fix it ranked 47th.

## Verify
<pending>
