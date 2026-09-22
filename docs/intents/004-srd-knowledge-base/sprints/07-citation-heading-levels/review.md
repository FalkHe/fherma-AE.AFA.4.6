---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
url: –
---
# Review: Sprint 07 — every rule is cited under its real heading

## What changed
Rules passages are now cited under the heading they actually sit beneath. Before, whenever the rulebook skipped a heading level, every later entry was filed under the first one: all spells appeared under "Acid Arrow", all creatures under "Ape", every condition under "Blinded". That affected 481 of the 1,750 passages. The rulebook has been re-loaded with the corrected citations; the passage count and the way text is split are unchanged, and the relevance cut-off was re-checked and holds.

## How to check it
- Ask "what does fire bolt do": the first answer is cited "Spell Lists › Spell Descriptions › Fire Bolt".
- Ask "what happens when a creature is frightened": cited "Adventuring › Conditions › Frightened".
- The rulebook status still reports 1,750 rules, loaded today.
- The eleven questions in the module documentation were re-run: every in-corpus one still answers, every off-topic one still says "no relevant rule", and the documentation table shows the new distances with no sibling-nested citation left.

## Heads-up
- Loading the rulebook from inside the container leaves the stored source file owned by root and unreadable to git on the host until its permissions are fixed. This sprint fixed it by hand; a proper fix is proposed in the backlog.
- Monster "Actions" and "Reactions" still live inside the monster's own passage. Making them separately citable is a retrieval change awaiting its own decision.

Brief: docs/intents/004-srd-knowledge-base/sprints/07-citation-heading-levels/brief.md

## Verdict
