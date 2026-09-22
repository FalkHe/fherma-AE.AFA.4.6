---
author: sprint
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 07: Every rule is cited under its real heading

## Task
Fix the way the rulebook is split into passages so that a heading's siblings are
no longer filed under the first sibling, then re-load the rulebook and confirm the
relevance cut-off still holds. Today 481 of 1,750 passages carry a wrong citation:
every spell is cited under "Acid Arrow", every creature under "Ape", every
condition under "Blinded", because the source skips heading levels and the
splitter only counts depth.

## Outcome
`app srd search "what does fire bolt do"` cites the passage as
"Spell Lists › Spell Descriptions › Fire Bolt" — no unrelated sibling in the trail —
and no passage in the re-loaded corpus is cited under a sibling heading.

## Acceptance criteria
- AC1: a source whose headings skip a level (a `##` followed directly by two `####`)
  yields two sibling citations, neither nested under the other (← D4).
- AC2: after re-ingest, `app srd search "what happens when a creature is frightened"`
  cites "Adventuring › Conditions › Frightened", and the fire bolt query above cites
  "Spell Lists › Spell Descriptions › Fire Bolt".
- AC3: the re-loaded corpus holds the same number of passages as before (1,750);
  only the citations changed, not how the text is split.
- AC4: the eleven questions the module documentation uses to justify the relevance
  cut-off are re-run against the re-loaded corpus and the documentation shows the
  new distances; every in-corpus question still answers and every off-topic one
  still says "no relevant rule" (← D7).
- AC5: the module documentation no longer shows a sibling-nested citation anywhere.

## Decisions
← D3, D4, D7

## Assumptions
- Only the heading trail changes; the splitter still stops at four heading levels,
  so a monster's "Actions" and "Reactions" stay inside the monster's passage. Making
  them separately citable is a retrieval change, not a bug fix, and is proposed
  separately (see Out of scope).
- The re-ingest costs roughly one US cent of embedding calls and replaces the
  corpus wholesale, as every ingest does.
- If the re-measurement shows the cut-off no longer sits in the gap between
  in-corpus and off-topic questions, the sprint re-pins it to the new measured
  value and says so plainly in the review, rather than shipping a cut-off the
  documentation contradicts. A human may veto this and ask for a separate decision.

## Out of scope
Splitting monster stat blocks into separately citable "Actions" / "Legendary
Actions" / "Reactions" passages (would add about 345 passages and change what a
creature question quotes — needs its own decision) · the player-facing citation
display · the playthrough empty-corpus guard and the DM agent's rules tool (intents
005 / 008).
