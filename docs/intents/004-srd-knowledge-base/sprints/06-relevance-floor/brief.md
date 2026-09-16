---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 06: "no relevant rule" is an answer, not an empty guess

## Outcome
`app srd search "<query>"` returns nothing and says so for a question the SRD does not cover, while still
answering one it does — the relevance floor is pinned to a measured value.

## Acceptance criteria
- AC1: `app srd search "how do I reload a plasma rifle"` prints "no relevant rule" and returns no passages (← D7).
- AC2: the same build still answers `app srd search "how does half cover work"` with the passages sprint 05 proved — raising the floor did not empty the useful case.
- AC3: `RELEVANCE_FLOOR` is a pinned module constant, and `modules/srd/README.md` records which queries were measured to choose it.
- AC4: a match below the floor is not returned at all — never with a warning, never as a "best effort" (← D7).
- AC5: the empty result is distinguishable from sprint 01's empty corpus: one is exit 0 with "no relevant rule", the other exit non-zero.

## Decisions
← D7

## Assumptions
- The floor is measured against the real ingested corpus, which is why this follows 03 and 05 rather than sitting inside them.
- It is a cosine-distance threshold on the operator the search already uses, not a percentage, and not a setting — it moves with the embedding model, which is pinned.
- A handful of hand-picked in-corpus and out-of-corpus questions are the measurement; no scored evaluation harness is built here.

## Out of scope
What the DM *says* when nothing comes back (phase 8's prompt) · the citation display (later stage) · any run-time tuning surface for the floor.
