---
author: sprint
owner: agent
created: 2026-09-15
updated: 2026-09-15
stage: draft
---
# Progress: Sprint 01

| WI | Status | Note |
|---|---|---|
| 1 | done | openrouter==0.10.8 resolved, 2 tests, pydantic floor intact |
| 2 | done | seam + Usage, 7 tests, commit pending verify |
| 3 | done | chat CLI + streaming, 6 tests, suite 146/146 |
| 4 | done | 3 docs corrected, commit 7cffdf6 |
| qa | done | AC2–AC5 green (6 tests); AC6 not suite-assertable, gate-verified |

Status: `open | running | done | failed`

## Issues
- Branch cut from a dirty `main`: the intent planning docs and the D4 `.env.dist` edit were uncommitted, so they ride in this sprint's MR as a separate `docs(intents)` commit.
- `.ai-backup/` and the deleted `.claude/` agent files are pre-existing and unrelated; left untouched.
- `AGENTS.md:61` and the `<TODO: not wired yet>` in `docs/architecture.md:15` were falsified by this sprint and outside WI4's scope; sprint lead corrected both at the gates.
- AC6 cannot be asserted from pytest: `app-cli` only has `backend/` (`docker/backend.Dockerfile` `COPY backend/ ./`, compose mounts `./backend:/app`), so repo-root docs and `.git` are invisible to the suite. Verified deterministically at the gate instead; the plan was wrong to ask qa for a fixture test.

## Backlog proposals
- Mount the repo root read-only into `app-cli` if a later sprint needs the suite to assert on docs or run `git grep`.

## Verify
