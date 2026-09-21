---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: draft
---
# Progress: Sprint 07a

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| 4 | open | |
| 5 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues

- **Sprint 07 was split into 07a and 07b** — the largest in the intent. Research could not fit under its own cap
  even compressed. 07a derives and records a roll; 07b spends it once and adds `awaiting`. 07b is issue #35, new;
  rows 08 and 09 now depend on 07b.
- **This plan still runs ~25% over the word cap after the split.** The overflow is contract — five producer
  signatures and their payloads — not scope: splitting further would separate the dice from their only callers.
  Recorded rather than split again.
- **Two rulings from the product owner**, asked because research marked them product-visible:
  1. The SRD's difficulty table binds authored content as well as the DM, so the authoring floor rises from 1 to
     5 (AC5). Their principle was "SRD rules win". The 5–30 range came from D6 and matches the SRD's own table;
     the old floor of 1 came from the content schema and matches nothing. Greenhollow's authored checks are 8, 10,
     12, 12, 13, 14, so nothing shipped breaks. **This reaches outside the sprint's module** — flagged in the
     review.
  2. A monster's attack is chosen by the DM **by name** and derived from its stat block, never by position.
- Called, agent-level: `passive_check` records a `tool_call` at `dm` rather than a `roll`, since a `roll` needs
  faces and would be consumable · `_acted_this_turn` belongs to sprint 08 · a dice expression is capped at 20 dice
  of at most 100 faces.

## Backlog proposals

<none yet>

## Verify
