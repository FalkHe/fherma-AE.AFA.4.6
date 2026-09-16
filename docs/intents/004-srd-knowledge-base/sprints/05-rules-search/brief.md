---
author: fhit:architect
owner: human
created: 2026-09-15
stage: approved
---
# Sprint 05: a rules question comes back with passages we can cite

## Outcome
`app srd search "<query>"` answers a rules question with SRD passages, best first, each carrying the
heading path that cites the rule it came from.

## Acceptance criteria
- AC1: `docker compose run --rm app-cli app srd search "how does half cover work"` prints passages that cover the question, most relevant first.
- AC2: each passage carries its heading path and ordinal — enough to point at the rule in the SRD — plus its score (← D4).
- AC3: `--limit` caps how many come back; omitted, it falls back to the module's `DEFAULT_LIMIT`.
- AC4: three unrelated questions (a condition, a combat action, a spell) each return passages from the matching SRD section, checked by eye in one run.
- AC5: the query is embedded through `core/llm` and matched by cosine distance against `srd_rules`; nothing outside `modules/srd` issues that query (← D1).
- AC6: searching an empty corpus exits non-zero with the empty-corpus message rather than printing an empty result (← D5).

## Decisions
← D1, D2, D4

## Assumptions
- Calls `embed_texts` unchanged — **blocked until intent 001 backlog 04 lands**.
- `search_rules(db, query, *, limit) -> list[RuleMatch]`; the CLI is a printer over it, and phase 8's `lookup_rule` will call the function, not the command.
- Ordering is cosine distance over sprint 01's HNSW index — no re-ranking, no keyword hybrid; scores are printed for the human eye, and whether a player sees one belongs to the later citation-display stage.

## Out of scope
The relevance floor and the "no relevant rule" signal (06) · the phase-8 tool binding · the player-facing citation display (later stage, ← D4/D6).
