---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research — sprint 05: rules search

## Facts

- Cosine query precedent, `playthrough/service.py:2596-2645` (`recall`): embeds once via
  `await asyncio.to_thread(llm_service.embed_texts, [query])` (:2628), then
  `select(...).order_by(Event.embedding.cosine_distance(vector)).limit(k)` (:2638). Distance is
  ordering only — no score exposed, no floor. Only the needed columns are selected, so no 1536-float
  vector crosses the wire.
- `embed_texts(texts, *, model=None) -> EmbeddingResult` (`core/llm/service.py:350`); `.vectors[0]`
  is the query vector, `.usage` the cost. Empty input raises `LlmBadRequestError`. Must be called
  attribute-style (`llm_service.embed_texts`) for monkeypatching. `ingest` calls it blockingly
  (`srd/service.py:354`); `recall` does not — search should follow `recall`.
- Index: `ix_srd_rules_embedding`, `hnsw` / `vector_cosine_ops` (`alembic/versions/0002_srd_rules.py:50`,
  mirrored in `srd/models.py`); used only when `ORDER BY <distance>` and `LIMIT` sit in one statement with no predicate on the
  ordering expression. pgvector 0.5.0 (`backend/uv.lock:819`,
  source: local lockfile) — `cosine_distance()` returns `<=>`, i.e. **distance in 0..2, lower = closer**.
- `require_corpus(db)` (`srd/service.py:78`) raises `SrdCorpusEmptyError` on an empty table;
  `check_vector_width()` (:44) fails a width mismatch before any query. CLI wiring and
  `EMPTY_CORPUS_MESSAGE` already exist (`app/cli.py:40`, `srd/commands.py`).
- Stale branch, commit `0c9c27f`: `search_rules(db, query, *, limit=DEFAULT_LIMIT)`, `DEFAULT_LIMIT = 5`,
  `require_corpus` first (an empty corpus costs no gateway call), then
  `distance = SrdRule.embedding.cosine_distance(v).label("distance")` selected alongside the row and used as
  `order_by` + `limit` in one statement; `score = 1 - distance` (similarity, higher better).
  `RELEVANCE_FLOOR` is **not** in that commit — sprint 06 added it later (`51089e3`) as `score >= 0.43`,
  in Python after the limited query (a SQL `WHERE` on the distance measured 8.475 ms seq scan vs 0.996 ms
  index scan).
- Ports cleanly onto main: the query construction, `require_corpus`-first ordering, `DEFAULT_LIMIT`,
  `RuleMatch`, the CLI printer and the basis-vector test recipe (`_basis`/`_diagonal`, `embed_texts` faked)
  — all touch only symbols main already has. Does **not** port: the stale `commands.py` docstring and error
  branches (main diverged), its `MAX_CHUNK_TOKENS` 800, and everything floor-related.
- **Corpus risk (verified live).** Main embeds `chunk.text` alone (`srd/service.py:354`), body without heading.
  In the ingested corpus (1750 rows) the row `Spell Lists › Spell Descriptions › Acid Arrow › Fire Bolt`
  has a body starting `*Evocation cantrip* … Casting Time … Range …` — the spell's own name appears
  **only in `heading_path`**, so every spell embeds as an interchangeable stat block. The stale branch hit this in
  sprint 05 (`f7932e3`: "fire bolt" ranked its own entry 47th) and fixed it by embedding the heading trail
  joined to the body, `SrdRule.text` still storing the body alone. AC4's spell question is unlikely to pass
  without that fix plus one re-ingest.

## Work items

- **WI1 (backend-python)** — `RuleMatch` in `schemas.py`; `DEFAULT_LIMIT = 5` and `search_rules` in
  `service.py`; `app srd search` in `commands.py`; README `Surface` entry. Include the heading-trail fix: in
  `ingest`, embed `f"{chunk.heading_path}\n\n{chunk.text}"` (stored `text` and `token_count` unchanged —
  the reported token count then understates by ~5 %, a README note), then re-ingest once.
  Tests: unit, with `embed_texts` monkeypatched and the session stubbed as `tests/srd/test_service.py` does
  (empty corpus raises before the gateway is touched; the query text reaches the seam; the default limit
  applies), plus `database`-marked tests over `srd_db` (`tests/srd/conftest.py`) inserting a few synthetic
  basis-vector rows for real ordering, limit and score values.
- **Live proof (sprint lead, not CI)** — after the re-ingest, run three questions by eye against the real
  corpus: a condition, a combat action ("how does half cover work"), a spell ("what does fire bolt do"), and
  record the printed heading paths and scores in `progress.md`. One embedding per run, negligible cost.

## Interfaces

```python
DEFAULT_LIMIT = 5

async def search_rules(db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT) -> list[RuleMatch]: ...

class RuleMatch(CamelModel):
    heading_path: str   # the citation trail, as stored
    ordinal: int        # position of the passage within its section
    text: str           # the passage body, as stored and as quoted
    score: float        # cosine distance (pgvector `<=>`), 0..2, LOWER IS CLOSER
```

`score` is the raw distance, not `1 - distance`: sprint 06's approved brief pins the floor as "a
cosine-distance threshold on the operator the search already uses", so the number printed here is the one
sprint 06 thresholds (as a *maximum*). Body: `check_vector_width()`,
`await require_corpus(db)`, `await asyncio.to_thread(llm_service.embed_texts, [query])`, then one statement
selecting the needed columns plus the labelled distance, `order_by(distance).limit(limit)`. No floor, no
re-ranking. Errors travel unwrapped; nothing commits.

CLI `app srd search "<query>" [--limit N]` prints one block per match, blank line between:

```
1. <heading_path> #<ordinal> (distance 0.412)
   <passage text, indented>
```

Empty corpus → `EMPTY_CORPUS_MESSAGE` on stderr, exit 1 (AC6). Non-positive `--limit` → one stderr line,
exit 1, before any gateway call. Blast radius: additive inside `modules/srd` plus one line in `ingest`.

## Open questions

- Re-ingesting the corpus so spell questions find the right spell costs one more embedding run (cents) and
  produces a diff in what was embedded. Confirm that is in scope for this sprint — without it, the spell
  question in AC4 is expected to fail.
