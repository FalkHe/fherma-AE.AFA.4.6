---
author: sprint
owner: agent
created: 2026-09-21
updated: 2026-09-21
stage: done
---
# Progress: Sprint 09

| WI | Status | Note |
|---|---|---|
| 1 | done | `attack` and `damage`, seven guards broken and caught |
| 2 | done | `roll_initiative`, and the schema-wide proof of no combat state |
| 3 | done | module doc §20-§22 and README, both left reading as finished |
| qa | done | 4 acceptance tests; AC4's last assertion reworked once |

Status: `open | running | done | failed`

## Issues

- **Not split**, unlike every sprint since 05. Research argued it plainly: the three mechanics reuse the gate
  order, the roll consumption and the one-action helper unchanged, only one new error code appears, and splitting
  would cut damage from the attack entry it binds to. 08b shipped four mechanics as one sprint.
- The plan runs over its word cap. The overflow is the two binding contracts, not scope.
- **One product-visible question is left open on purpose**: the SRD has a character at zero hit points *dying*,
  making death saving throws, not simply down. This sprint sets `down` and stops there, which is what the brief
  specifies; nothing yet narrates death saves, and nothing ends a run whose character never gets up. That belongs
  to phase 8, which narrates, and wants the product owner's ruling before it is built. Flagged in `review.md`.

- A coordination gap between two work items, caught before shipping: qa's AC4 asserted that a character's stored
  state gained the key `down` over the course of a fight, but `down` is a declared field written at creation, so
  the difference was always empty and the assertion could never hold. It now asserts the exact key set instead,
  which is what the criterion is really about, and the `down` false-to-true observation moved to AC2 where it
  belongs. qa proved the new form bites by adding a combat flag and a `fight_tracker` column and watching both be
  caught.

## Backlog proposals

- A critical hit costs its target no more than an ordinary hit, and a blow can be paid out only once, so the
  narrating layer cannot compensate. Making a crit hurt more means changing how wounding works.
- For phase 8: decide what a downed character does next — death saving throws as the SRD has them, stabilising,
  and whether a run whose only character stays down ends, and how.

## Verify

Round 1: approve — AC1-AC4 all OK, every one proven by mutation. The verifier added an `encounters` table, an
`objects.in_combat` column and a stored `turn_order` state key one at a time and watched each be caught; broke
each of damage's four binding guards; dropped the database's own hit-point constraint to prove the clamp is
tested rather than merely constrained; changed the crit to read the total instead of the die; made `attack`
write an object row; and replaced the whole-state reassignment with an in-place mutation, which silently lost
the write and failed three tests.

It also found the error summary in both documents claiming an unrecognised hit id answers *not found*, where the
code answers *not usable*. Corrected here — §22 already had it right, only the summary disagreed.
