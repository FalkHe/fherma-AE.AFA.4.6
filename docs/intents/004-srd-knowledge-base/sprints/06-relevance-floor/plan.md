---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 06 — "no relevant rule" is an answer

## What the measurement found
Twelve questions the rules answer and eleven they do not were measured against the real rulebook. **The two groups overlap**: the weakest real question scores 0.485, while four questions the rules genuinely do not cover score higher — up to 0.631 — because each is a near miss that lands on a generic feature the rules do carry. No floor separates them cleanly. The widest empty band is 0.371 to 0.452, so the floor goes at **0.40**: it keeps every real question with 0.085 to spare and rejects every topically alien one with 0.029 to spare.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | A weak match is not an answer: passages below the pinned floor are dropped entirely, never returned with a warning or as a best effort. | a match below the floor is absent from the result; a match above it is kept; a query whose every match is below the floor returns nothing; the cap still limits what comes back; the index is still used | I1 |
| 2 | backend-python | Asking something the rules do not cover says so plainly and reports success — it is an answer, not a failure — and stays distinguishable from asking an empty rulebook. | nothing relevant prints "no relevant rule" on stdout and exits 0; an empty rulebook still prints its own message on stderr and exits non-zero; a question with answers is unchanged | I1, I2 |
| 3 | backend-python | The project records what the floor is, which questions were measured to choose it, and what it does not protect against. | the module description carries the floor, the measured questions with their scores, the overlap finding and the two exit codes | I1, I2 |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I1, I2 |

## Interfaces
- **I1** — `backend/app/modules/srd/service.py`: `RELEVANCE_FLOOR = 0.40`, a pinned module constant, not a setting. `search_rules` keeps ordering by cosine distance **with** the `LIMIT` — measured, a `WHERE` on the distance destroys the index plan (0.996 ms indexed becomes 8.475 ms scanning), while filtering after the ordered, limited query keeps it at 0.367 ms — so the floor is applied in Python after the query, and `DEFAULT_LIMIT` becomes a cap on what may come back rather than a count of what will.
- **I2** — `backend/app/modules/srd/commands.py`: an empty result prints "no relevant rule" to **stdout** and exits **0**. The empty-corpus case keeps its existing message on **stderr** and its non-zero exit. These two must stay distinguishable.

## Decided here
- The floor is 0.40, for the margins above.
- The overlap is reported to the human rather than engineered around. The floor rejects questions alien to the rules; it cannot reject a D&D-flavoured question about material the rules omit, which still returns a plausible but wrong rule. That half of the promise belongs to the play stage's own prompt, and is raised as a proposal.

## Acceptance tests (qa)
- AC1 → asking how to reload a plasma rifle prints "no relevant rule" and returns no passages.
- AC2 → the same build still answers how half cover works with the cover rules.
- AC3 → the floor is a pinned module constant and the module description records which questions were measured to choose it.
- AC4 → a match below the floor is not returned at all — never with a warning, never as a best effort.
- AC5 → nothing relevant is exit 0 with "no relevant rule"; an empty rulebook is exit non-zero.

## Order
WI1, then WI2, then WI3. qa alongside from the start. Then the sprint lead re-checks both questions by eye.
