---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: running
---
# Progress: Sprint 03 — corpus ingested

| WI | Status | Note |
|---|---|---|
| 1 | done | `ingest` + `IngestReport` + unique citation constraint (migration 0009) ported from the stale branch, real `app srd ingest` wired; live run on 2026-09-22 10:09 UTC: `app srd status` → 1750 rules, openai/text-embedding-3-small; 1750 rows = 1750 distinct (heading_path, ordinal), max 1000 tokens; commits 38efcd3 8e7fadb ceaf313 |

Status: `open | running | done | failed`

## Issues
- The brief predates the `## Task` template section; its `## Outcome` matches backlog row 03, so no `/fhit:backlog` repair was run.
- No architect agent: the human asked for least effort and the sprint lead had already inspected the stale branch in the previous session turn; `research.md` records those facts.
- Branch name carries `-r2` because `origin/sprint/004-03-corpus-ingested` is the stale 2026-09-16 chain used only as a porting reference.
- `glab` is signed in as `f4lkh3`; MR assignee is set to `st3ll4` explicitly.

## Backlog proposals
- Sprint 04's core (wholesale delete-and-insert in one transaction, previous corpus kept on failure) is already in this port; sprint 04 may reduce to a verification-only pass.

## Gates
Lint (backend + frontend), backend suite (1008 passed), database-marked suite (148 passed) and frontend suite (54) all pass. The implementer was cut off by a session limit after committing; the sprint lead re-ran the gates and the live checks.

## Verify
