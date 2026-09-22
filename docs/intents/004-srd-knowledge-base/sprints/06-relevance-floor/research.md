---
author: sprint
owner: agent
created: 2026-09-22
---
# Research: sprint 004-06 — relevance floor (port from the stale branch)

## Facts
- `main` (after MR !46): `search_rules(db, query, *, limit=DEFAULT_LIMIT) -> list[RuleMatch]` orders by pgvector cosine distance and returns `score` = raw distance (lower is closer). No floor. `app srd search` prints one block per match; on `[]` it prints nothing and exits 0.
- Stale `origin/sprint/004-06-relevance-floor` applied `RELEVANCE_FLOOR = 0.43` as a *similarity* (1 − distance) minimum, filtered in Python after `ORDER BY … LIMIT` (a SQL `WHERE` on the distance dropped the planner from an HNSW index scan to a seq scan + sort). It printed `no relevant rule found for this query` on stdout, exit 0. Its README has a "Relevance floor" section with the measured queries.
- The floor must be re-measured: the corpus was re-embedded on 2026-09-22 13:04 UTC with heading trail + body, so the stale value does not carry over. Today's live distances: half cover → 0.515, frightened → 0.389, fire bolt → 0.440–0.486; lexical look-alikes (Half-Dragon, Half-Elf) at 0.64–0.70; Fireball behind Fire Bolt at 0.505.
- The brief pins the floor as a cosine-distance threshold (a maximum), a module constant, not a setting; README records the measured queries (AC3).

## Work items
WI1 (backend-python): `RELEVANCE_FLOOR` constant; Python-side filter `score <= RELEVANCE_FLOOR` in `search_rules` after order + limit; CLI prints `no relevant rule` on `[]` (stdout, exit 0); README section with the measurement table; unit tests; live measurement of ~5 in-corpus and ~5 out-of-corpus questions to pick the value.

## Open questions
None product-visible. The exact floor value is an agent measurement.
