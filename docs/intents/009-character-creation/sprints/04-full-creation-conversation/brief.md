---
author: fhit:architect
owner: human
created: 2026-09-22
stage: approved
---
# Sprint 04: the whole conversation

## Task
Complete the Tavern Keeper's conversation inside the graph of sprint 03: the three ways to set ability
scores, the backstory retold in the campaign's voice, two skills and an alignment proposed from that
story, and the class's either/or equipment choices. Each step is a tool over the sprint 02 builders and
the sprint 01 data; the prompt gains the order of the steps and the wording of the attachment.

## Outcome
A terminal player can spend points by hand, have the dice decide or take a suggested set, hear their own
backstory read back in the tavern's tone, and reach the review with two skills, an alignment and chosen
equipment on the sheet.

## Acceptance criteria
- AC1: The agent offers a suggested set for the class, rolling, or spending by hand; spending by hand
  shows the points left after every change, and rolled scores come from the game, never the agent (← D5).
- AC2: The player tells name, looks and story in free words in any order; the agent asks only for what is
  missing, reads it back in the campaign's tone and accepts corrections any number of times (← D6, D10).
- AC3: Two skill proficiencies are proposed from the story with a one-line reason each, and the player may
  name two others from the SRD skill list instead (← D7).
- AC4: One of the nine alignments is proposed with a reason, and the player may name another (← D13).
- AC5: The class's either/or equipment choices are walked one at a time with a plain-words hint, and "just
  the default" takes every remaining default in one turn (← D8).
- AC6: The review of sprint 03 now shows alignment, skills and equipment as well (← D9, D14).

## Decisions
← D5, D6, D7, D8, D9, D10, D13, D16, D18

## Assumptions
- Skills a class grants are filled in from its own list in SRD order without asking (← D18).
- The retold name, looks and backstory are what the sheet keeps; the player's raw words are not stored.
- Re-rolling scores is allowed until the player accepts a set.

## Out of scope
No web surface · no change to how a character is saved · no new SRD data beyond sprint 01 · no rules
lookup in the SRD corpus.
