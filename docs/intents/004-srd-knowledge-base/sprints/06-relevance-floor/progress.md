---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 06 — "no relevant rule" is an answer

| WI | Status | Note |
|---|---|---|
| 1 | done | matches below the pinned floor are dropped entirely; index plan unchanged |
| 2 | done | nothing relevant says so on stdout and exits 0, distinct from the empty rulebook |
| 3 | done | the module records the floor, the measured questions, the overlap and the exit codes |
| qa | done | one acceptance test per criterion; also reconciled the previous sprint's test, which had encoded that everything comes back regardless of score |

Status: `open | running | done | failed`

## Issues
- The measurement this sprint hangs on produced an uncomfortable result, reported rather than smoothed over: questions the rules answer and questions they do not **overlap**. The weakest genuine question scores 0.526, while two questions the rules genuinely do not cover score higher, up to 0.668 — and that strongest impostor beats seven of the twelve genuine questions. Each of those is a near miss — asking about a subclass or a setting the rules omit lands on a generic feature they do carry. A similarity score cannot tell "close topic, wrong rule" from "right rule".
- The measurement had to be taken twice. The first table recorded short labels rather than the questions actually asked, so nobody could reproduce it — three people re-running it got three different numbers. It was re-measured with the exact question text recorded for every row, which is what a reader needs to check the figure that a later decision will rest on.
- The floor moved as a result. The first value, 0.40, turned out to sit at the very bottom edge of the empty band, three thousandths above a question it was supposed to reject — close enough that rewording the question would have flipped it. It is now 0.43, in the middle of that band: the same questions are rejected, but with real room on both sides. It still cannot reject a plausible-sounding question about material the rules omit. Raised as a proposal for the human.
- One criterion asks that a question the rules do answer still answers after the floor goes in. It does, but with fewer passages: the cover question returned five before and returns one now, because ranks two to five were noise. That is the floor working, not a regression.
- The previous sprint's acceptance test had to be reconciled rather than an implementation fixed: it asserted that a wholly unrelated passage still came back, which this sprint deliberately overturns. Its real claim, that answers come back best first, is kept and sharpened.
- Sixth and last merge request in an unmerged chain.

## Backlog proposals
- The floor delivers half of what the decision behind it promises. It stops the rulebook answering questions alien to it, but a D&D-flavoured question about material the rules omit — a subclass, a setting's gods, a spell that is not in the document — still returns a plausible wrong rule above the floor. Seven of the eleven such questions measured score above the floor. Worth a decision before the play stage leans on this: either the play stage's own prompt carries that half, or the rulebook needs something a similarity score cannot provide.

## Gates
Lint, both suites and the live-database run all pass (650 offline, 35 live, 53 frontend).

By-eye against the real rulebook at the final floor: "How do I reload a plasma rifle?" and "How do I sharpen a kitchen knife?" both print `no relevant rule found for this query` and exit 0; "How does half cover work?" still answers with Combat > Cover at 0.531.

## Verify
<pending>
