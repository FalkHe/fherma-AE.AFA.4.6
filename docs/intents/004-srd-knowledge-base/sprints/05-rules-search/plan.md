---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 05 — rules search

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `app srd search "<query>" [--limit N]` returns SRD passages best first, each with heading path, ordinal and cosine-distance score; `search_rules` is the function phase 8 will call; `ingest` embeds the heading trail together with the body so spell names are findable; README updated; corpus re-ingested once | empty corpus exits before any gateway call (AC6); the query text reaches `embed_texts`; default limit 5 applies and `--limit` caps; non-positive limit exits 1 before the gateway; `database`-marked test with a few synthetic basis-vector rows proves real ordering by distance, limit and score values; ingest embeds `heading_path + "\n\n" + text` while stored `text` stays the body | – |

Single WI, ported from `origin/sprint/004-05-rules-search` (see research) with the score flipped to raw distance. No qa agent; the live three-question run is the human-visible proof.

## Interfaces
```python
# app/modules/srd/service.py
DEFAULT_LIMIT: int = 5
async def search_rules(db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT) -> list[RuleMatch]: ...
# body: check_vector_width(); await require_corpus(db); vector = embed_texts([query]) via llm_service (to_thread);
# one select of the columns + labelled cosine_distance, order_by(distance).limit(limit). No floor. Nothing commits.

# app/modules/srd/schemas.py
class RuleMatch(CamelModel):
    heading_path: str
    ordinal: int
    text: str
    score: float   # pgvector cosine distance (<=>), 0..2, LOWER IS CLOSER — sprint 06 thresholds this as a maximum
```
CLI output, one block per match, blank line between:
```
1. <heading_path> #<ordinal> (distance 0.412)
   <passage text, indented>
```
Empty corpus → existing `EMPTY_CORPUS_MESSAGE` on stderr, exit 1. Non-positive `--limit` → one stderr line, exit 1.

## Acceptance tests (qa)
- AC1, AC2, AC4 → live run of three questions (condition, "how does half cover work", "what does fire bolt do") recorded in `progress.md`.
- AC3 → unit tests on default and explicit limit.
- AC5 → inspection: only `modules/srd` issues the query; `database` test proves cosine ordering.
- AC6 → unit test: empty corpus exits 1 before the gateway is called.

## Order
WI1 alone.
