---
author: sprint
owner: agent
created: 2026-09-21
---
# Plan: Sprint 03

Prose only, three file sets no two agents share, run in parallel; then one read-only sweep. No test run — the
backlog rules this sprint is verified by reading the docs.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | claude | The model document says the DM's long-term memory is its own past narration, and the argument that once favoured a separate journal now reads as the case for the design that was built | AC1, AC2, plus the three entity-list mentions no criterion names | I1, I3–I6 |
| 2 | claude | The glossary, the architecture overview and the requirement map name one memory tool and no journal | AC3, AC4, AC5 | I1–I4 |
| 3 | claude | The 005 mechanics attachment lists the tools the DM actually gets | AC6 | I2 |
| 4 | claude | Proof that no document still presents a journal as part of the system, and that the shared sentences read alike everywhere | AC7 | WI1–WI3 |

## Interfaces
- **I1 — the one sentence (WI1, model document).** *The DM's long-term memory is its own past narration — every narration line is encoded as it is written and searched by meaning across the whole campaign run, across adventures.* The glossary's Event clause is its one-clause echo; no other document restates it.
- **I2 — the tool (WI2 and WI3, identical).** `recall(query)` — *long-term memory: searches the run's past narration by meaning.* No `add_journal_entry`, no `search_journal`, no `record_fact`, no journal write anywhere.
- **I3 — the recap is not a tool.** The most-recent-N recap is handed to the DM up front when a run resumes as a new chat (← D3); it appears in the model document's prose only, never in a tool table or a reads line.
- **I4 — scope and asymmetry.** The whole run, across adventures (← D5); only the DM's narration is encoded, never the player's typed text, which stays verbatim in the timeline (← D2).
- **I5 — failure.** An encoding failure is logged, the narration is written and shown as usual, and only that one line is not findable later; the player notices nothing (← D4). WI1 states it; no other document repeats it.
- **I6 — the known gap.** A narration line that was true can still come back as a hit after it stopped being true; contained by the recent turns already in the chat history and by hard canon — hit points, position, inventory, scene — living on objects and read by tool, never by search.

Present tense throughout: search ships in sprint 02, and these documents are design contracts, so no Stage-02 marker.

## Acceptance tests (qa)
None. AC7 is a search across the documents, run by WI4.

## Order
Parallel: WI1, WI2, WI3. Then: WI4.
