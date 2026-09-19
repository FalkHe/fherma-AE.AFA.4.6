---
author: Falk Hermann <307901131+falkhetc@users.noreply.github.com>
owner: human
created: 2026-09-18
updated: 2026-09-18
stage: approved
source: docs/roadmap/Stage-01/phases.md (Phase 6)
source: 135.md
milestone: https://gitlab.hermann.pm/f4lkh3/fherma-ae.afa.4.6/-/milestones/6
---
# Journal Memory

Stage-01, Phase 6. Phase 5 is on the way.

**Wish:** Facts are written and embedded during play and retrieved later by
similarity plus unconditional recency.

**Goal (from the phase):** Facts are written and embedded during play and
retrieved later by similarity plus unconditional recency.

**Preparation (from the phase):** Decide what a journal entry is and what the
retrieval policy is. The DM writes the journal itself through a tool — no
separate chronicler agent, no second writer.

**Steps (from the phase):**
- Implement the write path with embedding
- Implement retrieval
- Decide and implement the mitigation for re-injected player-derived text
- Prove semantic recall and recency recall separately

**Depends on:** phases 2 and 5. Parallel with phase 7.

**Questions to settle first (the human's words):** First of all we should
clarify the separation between journal and events. Is it different? Is it the
same? Can or should it be combined? If not, may we end up with two different
truths?

**Rule #1 (the human's words):** aim for the least-effort implementation for
Stage 01. We still could remove features / complexity in this stage and add it
later — as long as we fulfil `135.md` in Stage 01.
