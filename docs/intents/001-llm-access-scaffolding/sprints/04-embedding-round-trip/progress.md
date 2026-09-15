---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: draft
---
# Progress: Sprint 04

| WI | Status | Note |
|---|---|---|
| 1 | open | |
| 2 | open | |
| 3 | open | |
| qa | open | |

Status: `open | running | done | failed`

## Issues
- Branched off `sprint/001-03-quiet-retry`, not `main`: !6 was still open and both sprints edit `service.py`. Embeddings therefore inherit D6's retry. **!6 must merge before this sprint's MR.**
- The intent research's premise for this sprint was wrong — it assumed embeddings needed raw `httpx` because LangChain drops `usage.cost`. The SDK exposes embeddings directly with cost first-class. Re-verifying before building saved a parallel error path.

## Backlog proposals

## Verify
