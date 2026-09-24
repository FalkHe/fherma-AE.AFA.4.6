---
author: fhit:architect
owner: human
created: 2026-09-24
updated: 2026-09-24
stage: draft
---
# Sprint 09: The old game flow is gone

## Task
Delete the old tool collection, guard step, combat-specific steps, message-based state, the old system prompt and every test asserting them; remove the generated flow diagram; and update the module, architecture, requirement-map and documentation index so they describe the new flow only, including how rules lookup and history recall now work as read-only aids to decisions.

## Outcome
No reference to the replaced flow remains in code, tests or docs, and the suite and linter pass.

## Acceptance criteria
- AC1: Given a search for the removed names, then nothing matches.
- AC2: Given the generated flow diagram, then it no longer exists.
- AC3: Given the module, architecture and requirement-map documents, then they describe the five-part flow and its two read-only aids.
- AC4: Given the full backend suite and linter, then both pass.

## Decisions
← intent §9.7–§9.10; AC "no obsolete graph code, tests, prompts, imports, or generated artifacts remain"

## Assumptions
- Route, authentication, transcript and playthrough tests are kept; obsolete node, tool and prompt tests are deleted rather than ported.

## Out of scope
New tests, frontend changes.
