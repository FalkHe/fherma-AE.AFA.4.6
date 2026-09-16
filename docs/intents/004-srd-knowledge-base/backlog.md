---
author: fhit:architect
owner: human
created: 2026-09-15
updated: 2026-09-15
stage: approved
---
# Backlog

Sprint outcomes, dependency-ordered. Status: `open | running | done`.

| # | Outcome (one verifiable statement) | Depends on | Issue | Status |
|---|---|---|---|---|
| 01 | `app srd status` on a migrated, never-ingested database reports an empty corpus and exits non-zero, and a vector width that disagrees with `EMBEDDING_DIMENSIONS` fails the same way instead of being accepted | – | #8 | done |
| 02 | `app srd ingest --dry-run` fetches SRD 5.1 from the CC-BY source into `backend/content/srd/v1/`, reports how many citable chunks it would embed, and a changed upstream shows up as a git diff | – | #9 | open |
| 03 | `app srd ingest` embeds the stored source and the corpus goes from empty to populated: the run prints chunk count, tokens and USD cost, and `app srd status` then reports rows, model and ingest time | 01, 02 | #10 | open |
| 04 | Running `app srd ingest` a second time replaces the corpus wholesale — the row count is the same, nothing is duplicated, and a run that fails part-way leaves the previous corpus intact | 03 | #11 | open |
| 05 | `app srd search "<query>"` answers a rules question with SRD passages, best first, each carrying the heading path that cites the rule it came from | 03 | #12 | open |
| 06 | `app srd search "<query>"` returns nothing and says so for a question the SRD does not cover, while still answering one it does — the relevance floor is pinned to a measured value | 05 | #13 | open |

## Notes

- 01 and 02 have no predecessor and may run in parallel: 01 is database-only
  (migration, table, status), 02 is filesystem-and-network-only. Neither needs an
  embedding call.
- **03–06 are blocked on intent 001 backlog 04** (`embed_texts` plus the
  `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` settings fields), still `open`. No
  sprint here implements it — it belongs to that intent.
- 01 carries **both roadmap open decisions assigned to this phase**
  (`docs/roadmap/Stage-01/README.md:313`-`:314`): the migration's vector width plus
  the mismatch check, and how a DB-backed test gets a real engine against a suite
  that never constructs one. Phase 3 inherits the latter.
- 01 also lands `require_corpus`, the guard D5 names, provable here only through
  `app srd status` and its unit test — **the playthrough-creation caller is phase
  5**, so that half of D5 is proven there, not here.
- D7's floor cannot be picked before a corpus exists to measure against, which is
  why 06 sits behind 05. 02's `--dry-run` exists so D3's fetch/store/chunk half is
  mergeable before `embed_texts` lands; 03 is the same command without the flag.
- No screen this phase, by design — "using the product" is the `app srd …`
  commands (← D2).
- Coverage: D1 → 01, 03, 05 · D2 → 01–06 · D3 → 02, 03, 04 · D4 → 02, 05 · D5 →
  01 **in part**, its playthrough caller **covered by no sprint here** (phase 5) ·
  D6 → 02 (README + `LICENSE.md`); its UI display **covered by no sprint here**
  (later stage) · D7 → 06.

## Proposals

<none yet>
