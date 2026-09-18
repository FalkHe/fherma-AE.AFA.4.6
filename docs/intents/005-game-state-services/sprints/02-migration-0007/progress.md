---
author: sprint
owner: agent
created: 2026-09-18
updated: 2026-09-18
stage: done
---
# Progress: Sprint 02

| WI | Status | Note |
|---|---|---|
| 1 | done | revision 0007, models, engine-free tests rewritten |
| 2 | done | module README and playthrough doc |
| qa | done | 4 database acceptance tests, red before implementation |

Status: `open | running | done | failed`

## Issues

- `AGENTS.md → Workflow` names the agent account `st3lla`; `glab` is signed in as `st3ll4` (display name Stella).
  Same account, leetspeak spelling; treated as a typo and the run continued.
- The merge request was approved by the agent account that authored it, which is the provider step the workflow
  prescribes; the human remains the reviewer and the only one who merges.
- Research's WI1 and WI3 were merged into one work item: the model change breaks the tests that pin the old sets, so
  splitting them would leave the suite red between two commits.

## Backlog proposals

- `downgrade` restores `template_id NOT NULL` and would fail on a database that already holds a generated character
  — safe until sprint 04 lands character creation, then worth revisiting.

## Verify

Round 1: approve — AC1-AC4 all OK; the verifier rebuilt two scratch databases to confirm the downgrade restores
`0006`'s constraint definitions, default and nullability byte for byte. No failed criteria.
