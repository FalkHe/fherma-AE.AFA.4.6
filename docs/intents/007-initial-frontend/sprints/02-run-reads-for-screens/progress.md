---
author: sprint
owner: agent
created: 2026-09-22
updated: 2026-09-22
stage: draft
---
# Progress: Sprint 02

| WI | Status | Note |
|---|---|---|
| 1 | done | List read shipped with its unit and route tests; full backend suite green. |
| 2 | done | Overview read shipped; tests red before green, full suite and the opt-in database suite green. |
| 3 | done | Typed client regenerated; diff purely additive, existing run block byte-identical. |
| qa | done | 5 acceptance tests, AC1-AC5; AC4 is `database`-marked, AC5 is a frontend check on the generated client. |

Status: `open | running | done | failed`

## Issues
- Research raised two questions it marked product-visible; both were decided here rather than escalated. The shipped campaign holds one adventure, so the brief's "0 of 3" example reads "0 of 1" against real content — the reads state facts, seeding more content is not this sprint's work. An unavailable run answers 200 with the flag rather than not-found, because D7 has the dashboard explain why it cannot be opened, which needs the run to be readable, and because not-found would be indistinguishable from a refusal.
- Technical calls left to the agent: the new `/runs` path family (a literal sibling of `/campaign/{run_id}` would shadow), the 200-character intro limit, and `playerCount` riding along in the list so sprint 07 need not reopen the schema.

## Backlog proposals

## Verify
