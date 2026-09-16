---
author: sprint
owner: agent
created: 2026-09-16
---
# Plan: Sprint 05 — a rules question comes back with passages we can cite

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | Asking the rulebook a question in plain words returns the passages that answer it, best first, each carrying the citation it came from and how well it matched; asking an empty rulebook says so instead of returning nothing. | closest passage ranks first and ordering follows similarity; the cap limits how many come back and defaults when omitted; an empty corpus raises the empty-corpus error before any gateway call; the query is embedded through the shared gateway seam | I1 |
| 2 | backend-python | Asking a rules question from the command line prints the answers with their citations and scores; a failure is one plain line. | results print citation, score and passage, best first; the cap flag limits them; an empty corpus exits non-zero with the empty-corpus message; a gateway failure is one stderr line and exit 1, no traceback | I1, I2 |
| 3 | backend-python | A rule can be found by its own name: what gets learned about a passage includes the heading trail that names it, not only its body. | the text sent to the embedder carries the heading trail; the passage stored for quoting is unchanged; after re-learning, asking for a spell by name returns that spell first | I3 |
| qa | qa | Black-box acceptance tests, one per criterion. | below | I1, I2 |

## Interfaces
- **I1** — `backend/app/modules/srd/schemas.py`: `class RuleMatch(CamelModel): heading_path: str; ordinal: int; text: str; score: float` (score is `1 - cosine_distance`; higher is better). `backend/app/modules/srd/service.py`: `DEFAULT_LIMIT = 5`; `async def search_rules(db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT) -> list[RuleMatch]`, which calls `require_corpus` first, then embeds the query through `embed_texts`, then orders by `SrdRule.embedding.cosine_distance(vec)` **with** a `LIMIT` — the limit is what engages the index (measured: 0.63 ms indexed against 8.5 ms without).
- **I2** — `backend/app/modules/srd/commands.py`: `app srd search QUERY [--limit N]`; exit 0 on results, exit 1 plus one stderr line on `SrdError` or `LlmError`. It never issues a query itself.
- **I3** — `backend/app/modules/srd/service.py`: the text handed to `embed_texts` during import is the heading trail joined to the passage body. `SrdRule.text` still stores the body alone, which is what gets quoted.

## Decided here
- **A rule must be findable by its own name.** Measured against the live corpus, "what does fire bolt do" ranks the actual Fire Bolt spell 47th, because only a section's body is embedded and a spell's name lives in its heading. AC4 requires a spell lookup to work by eye, so this sprint fixes what gets embedded and re-imports. Conditions and combat actions already rank first.
- Five results by default.

## Acceptance tests (qa)
- AC1 → asking how half cover works prints passages covering the question, most relevant first.
- AC2 → each passage carries its citation and position — enough to point at the rule — plus its score.
- AC3 → the cap limits how many come back; omitted, it falls back to the module default.
- AC4 → a condition, a combat action and a spell each return passages from the matching section.
- AC5 → the query is embedded through the shared gateway and matched by cosine distance; nothing outside the rules module issues that query.
- AC6 → searching an empty rulebook exits non-zero with the empty-corpus message rather than printing nothing.

## Order
WI1, then WI2 and WI3 in parallel. qa alongside from the start. Then the sprint lead re-imports and checks the four questions by eye.
