---
author: sprint
owner: agent
created: 2026-09-19
updated: 2026-09-19
stage: draft
---
# Progress: Sprint 05a

| WI | Status | Note |
|---|---|---|
| 1 | done | `append_event`, twelve payload models, the only-writer guard |
| 2 | done | `list_events` and the events read route |
| 3 | done | module doc §9 and README, with the id-ordering caveat |
| qa | done | 3 acceptance tests; AC5 reworked once, it had skipped silently |

Status: `open | running | done | failed`

## Issues

- **Sprint 05 was split in two on the product owner's instruction.** The combined plan ran 28% over the size cap
  and research said the same: one sprint carried four surfaces. 05a is the writer and the read, 05b the cost
  command and the live signal. Both briefs are the approved brief's own text, partitioned — nothing added. The
  combined sprint directory was removed; its brief survives in git history and in the two halves.
- Backlog row 05 became rows 05a and 05b; 05b is issue #33, new. Rows 06 and 07 depended on "05" and now depend
  on 05a alone, which is all their work needs.
- Research is copied unchanged into both halves rather than referenced across directories.
- `compose.yaml` now mounts `./docs` read-only into the CLI container. AC5 asserts on a document the test
  container could not see, so its test skipped in every environment — green forever, proving nothing. Several
  later phases ship documentation criteria and now have somewhere to look.

## Backlog proposals

<none yet>

## Verify

Round 1: changes-requested — AC2 and AC5 OK; AC1's only-writer guard matches a bare `Event(` call but not
`models.Event(`, the attribute form that `AGENTS.md`'s own cross-module rule prescribes and that sprints 06-09
will use. The verifier proved it by adding a second writer in that form and watching both tests still pass.
