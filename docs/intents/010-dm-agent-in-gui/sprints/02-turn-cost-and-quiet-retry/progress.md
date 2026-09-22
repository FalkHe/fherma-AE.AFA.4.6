---
author: sprint
owner: agent
created: 2026-09-23
updated: 2026-09-23
stage: draft
---
# Progress: Sprint 02

| WI | Status | Note |
|---|---|---|
| 1 | done | async entry point with shared retry and classification |
| 2 | done | narration routed through the seam and carrying the turn's summed cost |

Status: `open | running | done | failed`

## Issues
Accepted the architect's assumptions: the query embeddings inside rule lookup and recall stay uncounted (chat tokens dominate), and a turn interrupted by a question or roll books its whole model cost on the resumed leg's narration — the run total stays exact, the per-turn split does not.

## Backlog proposals

## Verify
