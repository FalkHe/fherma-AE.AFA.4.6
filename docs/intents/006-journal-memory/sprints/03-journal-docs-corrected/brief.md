---
author: fhit:architect
owner: human
created: 2026-09-18
stage: approved
---
# Sprint 03: the docs describe the memory the product has

## Task
Rewrite the three affected sections and the first known gap of `docs/general/model.md`, drop the journal-entry term
from `docs/general/glossary.md`, replace the journal tool row in `docs/general/architecture.md` with the single recall
tool, restate the long-term-memory half of the Medium 2 row in `docs/general/requirement-map.md`, and correct the tool
list in `docs/intents/005-game-state-services/decisions/mechanics.md` so `record_fact` is gone and `recall` searches
narration. Each rewritten section states the chosen design and why the previously rejected one-table alternative is
now the ruling; the known gap describes narration going stale rather than a mis-retrieved journal entry.

## Outcome
Searching the general docs, the architecture doc and the 005 mechanics attachment for a journal, a journal entry or a
fact-writing tool returns nothing that describes them as part of the system, and the model document states in one
place that the DM's long-term memory is its own past narration, searched by meaning across the whole campaign run.

## Acceptance criteria
- AC1: `docs/general/model.md` — "Events and journal are two things", "One embedding model, two tables" and the
  journal sentence of "Situational facts have no flag store" are rewritten to the chosen design: narration events
  carry an optional vector, searched by meaning across the run, recap by recency on return, embedding failure never
  fails a write; the rejected-alternative paragraphs are inverted, not deleted (← D1–D5).
- AC2: `docs/general/model.md` Known gap 1 describes stale narration (a fact once true still returned as a hit) and
  its containment (recent turns in the chat history; hard canon on objects, read by tool).
- AC3: `docs/general/glossary.md` loses "Journal entry"; "Event" gains the clause that narration events are the
  DM's long-term memory.
- AC4: `docs/general/architecture.md` tool table: `add_journal_entry() / search_journal()` becomes `recall(query)`
  — long-term memory, search of past narration.
- AC5: `docs/general/requirement-map.md` Medium 2 row reads checkpointer (short) and narration search by meaning (long).
- AC6: `docs/intents/005-game-state-services/decisions/mechanics.md` reads section: `record_fact(text)` removed,
  `recall(query)` described as a search over the run's narration; the D-list of 005 is not touched.
- AC7: `grep -ri journal docs/general docs/architecture.md docs/intents/005-*/decisions/mechanics.md` returns only
  lines that name the journal as a rejected or Stage-02 alternative.

## Decisions
← D1, D2, D3, D4, D5

## Assumptions
- `docs/roadmap/` is history and stays as written; the phase 9 "journal view" step is retired through the backlog
  proposal, not by editing the roadmap.
- The 005 `decisions.md` D-list is human-owned and approved; only the `mechanics.md` attachment's tool list changes,
  since it names a tool that no longer exists.

## Out of scope
No code · no `docs/modules/playthrough.md` change (01 and 02 own their module README lines) · no roadmap edits.
