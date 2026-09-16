---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| 4 | open | |

Status: `open | running | done | failed`

## Issues
- Only sprint of this intent needing a real database. AC1/AC2/AC3/AC5 are hand-run; AC4/AC6 are the automated part and must stay engine-free.
- Research asked for a human ruling on `model.md:227`-`231`. Judged a documentation-accuracy matter, not product-visible: the doc names a schema mechanism that does not exist, and standing inaccuracies in these docs have already misled three sprints. WI4 amends it.
- Research left a dev database volume `fherma-aeafa46_postgres-data` that it created (removal was denied by the permission system). Left in place deliberately — this sprint needs a database for its hand-run checks, and deleting a database volume unprompted is not reversible.

## Backlog proposals
- Should `checkpoint setup` join `alembic upgrade head` in `entrypoint-web.sh` for phase 7? Out of scope here.

## Verify
