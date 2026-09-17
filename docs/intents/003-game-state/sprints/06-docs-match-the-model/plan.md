---
author: sprint
owner: agent
created: 2026-09-17
---
# Plan: Sprint 06 — the general docs describe the model that exists

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | claude | The five general documents describe the model that was built: the old entity name gone, position belonging to the creature, combat and turn order read as deferred, several characters per person stated. | Searching the general documents for the abandoned entity name returns nothing · combat and turn order appear only as explicitly deferred · no general document names an entity the schema does not have | I1 |
| 2 | claude | A document for the new module — what it owns, its five tables, its surface — and the documentation index listing it. | The module document exists and matches what the module's own readme says it owns · the index lists it | I1 |
| 3 | claude | The roadmap's register of open questions marked closed where this phase closed them, and nothing else in the roadmap touched. | Exactly six rows change · no other roadmap text differs | I1 |

The five general documents are one argument in one voice, and one of them carries two thirds of the corrections; splitting them across writers would diverge faster than a single pass costs. WI2 and WI3 draw on different sources and different files, so they are genuinely parallel.

## Interfaces
- **I1 — the shared vocabulary, binding on all three.** Take the term table **verbatim** from `research.md → Interfaces`: which words to write for the container, the adventure, the membership, the other three tables, the module, combat and turn order, position, several characters, and the seed player character — and which words never to write. Two writers using different words for one thing is the only way this sprint can fail.
- The corrections themselves are enumerated in the intent's model attachment, §7, items 1–19, each with the file and line it applies to. Every one still resolves. This sprint applies that list and adds nothing to it; anything else found goes to `progress.md` under Backlog proposals.

## Acceptance tests (no qa agent)
This sprint changes no code, so there is nothing to test at runtime and no acceptance suite. Its criteria are checked by reading and by search, at the gate: the abandoned entity name absent from the general documents, combat and turn order deferred rather than promised, the new module document present and listed, exactly six roadmap rows changed, and the existing suites still green because nothing under `backend/` or `frontend/` was touched.

## Order
Parallel: WI1, WI2, WI3 — no two touch the same file. Gates last.
