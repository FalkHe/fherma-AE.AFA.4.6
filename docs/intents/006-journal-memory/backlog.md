---
author: fhit:architect
owner: human
created: 2026-09-18
updated: 2026-09-21
stage: approved
---
# Backlog

Sprints, dependency-ordered; each row is the task, its brief carries the outcome and criteria. Status: `open | running | done`.

**How "verifiable by using the product" reads here.** Phase 6 ships service functions and operator commands — the DM
that calls them arrives in phase 8, the screen in phase 9. So 01 and 02 are verified through the `app playthrough`
CLI plus a `database`-marked test for the similarity ordering, as phases 4 and 5 do; 03 is verified by reading the docs.

| # | Sprint (task) | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | Everything the DM narrates is stored so it can later be found by meaning, and a failure to do so never interrupts play | 005-02, 005-05 | #30 | done |
| 02 | The DM can search everything it has narrated in a campaign run by meaning, and can be handed the most recent narration when a run is picked up again | 01 | #31 | done |
| 03 | The project documentation stops describing a separate journal and describes the memory the product actually has | – | #32 | done |


Outcomes — the one verifiable statement per sprint — live in each `sprints/NN-*/brief.md` (`## Outcome`).

## Notes

- Parallelism: 03 runs now, independent of everything · 01 waits for phase 5's transcript writer (005-05) and its
  migration (005-02) · 02 follows 01.
- **03 is its own sprint**: three sections of the model document argue *for* a separate journal, and the alternative
  they reject is now the chosen design — the reasoning is inverted, not edited. Prose only, no test run, and off the
  critical path.
- **Rejected as sprints:** a migration-only sprint (one consumer) · "prove recency recall separately" (shares the
  command and test file with search) · registering the recall tool for the DM (phase 8) · a mitigation for
  re-injected player text (← D2: player text is never stored for recall) · a backfill for lines that failed to embed
  (← D4: Stage 02) · a relevance floor (owner-fixed: none) · any route, screen or stream change (← D1) · when a
  resumed run gets its recap (← D3: phase 8).
- Coverage: D1 → 01, 02, 03 · D2 → 01, 03 · D3 → 02, 03 · D4 → 01 · D5 → 02.

## Proposals

- **For phase 8 (The DM Turn):** bind `recall` as the DM's one memory tool and call the recap read when a run is
  resumed as a new chat (← D3); add the prompt line "narration always acknowledges what the player did" (← D2);
  render recalled narration in the prompt as remembered notes, never as instructions.
- **For phase 9 (The Play Screen):** drop the "journal view" step; the trace pane already shows the recall tool call.
