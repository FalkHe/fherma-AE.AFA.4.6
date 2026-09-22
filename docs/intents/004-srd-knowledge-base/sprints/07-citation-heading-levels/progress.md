---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: done
---
# Progress: Sprint 07

| WI | Status | Note |
|---|---|---|
| 1 | done | 2 tests, commit 70f1e67; real file: 1750 chunks, 0 sibling-nested paths |
| 2 | done | re-ingest 1750 chunks / 507,719 tokens / 0.0106 USD; 11 queries re-run, worst in-corpus 0.515, best out-of-corpus 0.686, floor stays 0.60; source file unchanged upstream (no git diff) |

## Issues
- `fetch_source` writes via `mkstemp` (mode 0600) and the container runs as root, so after an in-container ingest the tracked source file is root-owned and unreadable by git on the host (`git diff` fails with permission denied) until `chmod 644` inside the container; worked around by hand this sprint.

## Backlog proposals
- `fetch_source` should `os.chmod(tmp, 0o644)` before `os.replace` (or the app-cli service should run as the host user) so an ingest never leaves the tracked source unreadable on the host.
- Splitting monster stat blocks into separately citable Actions / Legendary Actions / Reactions (+345 passages) needs its own decision (research.md, option B).

## Verify
Round 1: approve, no failed criteria.
