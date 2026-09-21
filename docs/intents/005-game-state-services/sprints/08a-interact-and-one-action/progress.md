---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: draft
---
# Progress: Sprint 08a

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues

- **Sprint 08 was split into 08a and 08b**, following the precedent of 05, 06 and 07. 08a is `interact` and the
  one-action-per-turn rule; 08b the inventory moves and the `use_item` seam. 08b is issue #36, new.
- **Two rulings from the product owner**, asked because research marked them product-visible:
  1. **Dropping an item is free.** The brief's own assumption counted `drop` as an action, while
     `decisions/mechanics.md` and the SRD both make it free; their standing rule is that the SRD wins. The brief
     line is superseded, and the action set lands here in 08a: `interact`, `take`, `give`, `use_item`, `attack`.
  2. A container standing in the scene can be looted, so Greenhollow's stolen fleeces can come out of the wool
     sack. That reaches 08b, where taking lives, and is written into its brief as AC5.
- `attack` is in the action set from this sprint, so the parallel sprint 09 needs no edit to it.
- With no turn allocator yet, every mechanic lands in one untagged turn. Each test scenario therefore mints its
  own `turn_id`, or a creature's second action anywhere in a run would be refused.

## Backlog proposals

<none yet>

## Verify
