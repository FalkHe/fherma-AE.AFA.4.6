---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 06 — relevance floor

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `app srd search` answers "no relevant rule" for a question the SRD does not cover and still answers in-corpus questions; `RELEVANCE_FLOOR` is a pinned module constant measured against the live corpus and recorded in the README with the queries used | a match with `score > RELEVANCE_FLOOR` is dropped silently; matches at or below it are returned in order; the CLI prints `no relevant rule` on stdout with exit 0 for `[]`; the empty-corpus path still exits 1 with the empty-corpus message; a `database` test with synthetic vectors shows a far row filtered and a near row kept | – |

Single WI, ported from `origin/sprint/004-06-relevance-floor` with the score semantics flipped to distance. No qa agent; the live measurement is the proof.

## Interfaces
```python
# app/modules/srd/service.py
RELEVANCE_FLOOR: float   # cosine distance maximum, pinned after measurement; not a Settings field
# search_rules: unchanged signature; after order_by(distance).limit(limit) fetch, keep rows with distance <= RELEVANCE_FLOOR
```
CLI: `[]` → stdout `no relevant rule`, exit 0. Empty corpus → unchanged (stderr, exit 1). Distinguishable per AC5.

## Acceptance tests (qa)
- AC1/AC2 → live: "how do I reload a plasma rifle" prints `no relevant rule`; "how does half cover work" still returns Combat › Cover first.
- AC3 → README section + constant.
- AC4 → unit test: above-floor rows are absent from the result, no warning.
- AC5 → unit tests on exit codes for `[]` vs empty corpus.

## Order
WI1 alone.
