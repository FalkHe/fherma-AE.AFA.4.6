---
author: sprint
owner: agent
created: 2026-09-26
---
# Plan: Sprint 09

Most of the removal already exists as an unstaged change on the branch (old nodes, state, tools, system prompt, guard step, obsolete tests, module README, general docs, refactoring notes). The plan covers only what research found still missing.

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | No code or test still names the old flow: the character-agent docstring stops describing removed game steps, the orphan `game/prompts/v1/system/smoke.md` is gone, and the checkpoint fixtures in the play-command tests use the current step names | play-command tests still pass with current step names | – |
| 2 | backend-python | `docs/architecture.md` describes the current system (all modules, the five-part game flow, its two read-only aids) instead of the scaffolding era; `docs/README.md` has no row pointing at a missing file | none (docs) | – |
| 3 | sprint | The generated old-graph diagram `docs/intents/008-headless-dm-agent/agent-graph.png` is deleted | none | – |
| 4 | sprint | Linter and full backend suite green; a repo-wide search for the removed names finds nothing | AC1, AC4 | 1, 2, 3 |

## Interfaces
None — WI1–WI3 touch disjoint files.

## Acceptance tests (qa)
No qa agent: the brief allows no new tests. AC1 and AC4 are checked by WI4, AC2 by WI3, AC3 by WI2 plus the already changed README, architecture and requirement-map documents.

## Order
WI1, WI2, WI3 in parallel; then WI4.
