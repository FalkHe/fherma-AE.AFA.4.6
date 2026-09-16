---
author: sprint
owner: agent
created: 2026-09-16
updated: 2026-09-16
stage: draft
---
# Progress: Sprint 03 — the corpus is ingested

| WI | Status | Note |
|---|---|---|
| 1 | running | |
| 2 | open | |
| 3 | running | |
| qa | running | |

Status: `open | running | done | failed`

## Issues
- Branched off sprint 02, which is branched off sprint 01; neither is merged yet, so this is the third merge request in a chain. Each targets its predecessor and will retarget on merge. The chain is getting long enough to be worth the human's attention.
- The criterion asking that a failed import leave no rows was written assuming one transaction spanning the whole run. Taken literally that would hold a database connection open across a minute of network calls for no gain, so the promise is kept a different way: every vector is obtained first, then written in one short transaction. What a user would notice is identical.
- The import prints one line per batch of progress rather than running silent for about a minute.
- If the gateway prices only some batches, the run reports the sum it knows and says the figure is incomplete, rather than hiding it.
- The criterion for the live import is written as a human's own run with a real key. The key is configured here and the run costs about one US cent, so the sprint lead runs it rather than shipping two criteria unproven; the actual cost is reported.

## Backlog proposals
<none yet>

## Verify
<pending>
