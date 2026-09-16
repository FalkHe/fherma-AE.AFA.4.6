---
author: fhit:architect
owner: agent
created: 2026-09-16
updated: 2026-09-16
---
# Research: sprint 05 — rules search

## Facts

**Query shape.** `pgvector 0.5.0` (`backend/uv.lock:678`, source: context7 `/pgvector/pgvector-python`)
exposes `cosine_distance` on the mapped column: `SrdRule.embedding.cosine_distance(vec)` returns a
`Float` expression usable both in `order_by` and as a labelled select column. SQLAlchemy 2.0.52
(`backend/uv.lock:990`), async session as everywhere else in the module.

**The HNSW index needs the `LIMIT`.** Measured with `EXPLAIN ANALYZE` on the 2,132-row dev corpus:
`ORDER BY embedding <=> $1 LIMIT 5` → `Index Scan using ix_srd_rules_embedding`, 0.63 ms. The same
statement *without* `LIMIT` → `Seq Scan` + `Sort`, 8.5 ms. So the limit is not a convenience, it is
what engages `ix_srd_rules_embedding` (`backend/app/modules/srd/models.py:44`).

**`RuleMatch`** (`module-structure.md` §3): `heading_path`, `ordinal`, `text`, `score` — a `CamelModel`
beside `RuleChunk` (`backend/app/modules/srd/schemas.py:17`). `score` is recommended as *similarity*,
`1 - cosine_distance`, higher is better, which is what the CLI prints.

**Embedding one query.** `llm_service.embed_texts(["…"], model=…)` returns an `EmbeddingResult`
(`backend/app/core/llm/service.py:78`) whose `.vectors[0]` is a 1536-float list; measured cost per query
≈ $1e-7. Call it attribute-style through the module reference, as `ingest` does
(`backend/app/modules/srd/service.py:401`), so tests can monkeypatch it.

**Session + printing.** `status` opens its own session via `get_sessionmaker()` inside an
`asyncio.run(...)` helper and echoes plain lines (`backend/app/modules/srd/commands.py:52`);
`search` mirrors it. Typer argument + option precedent: `backend/app/core/llm/commands.py:81`.

**AC6 is "call it first".** `require_corpus` already raises `SrdCorpusEmptyError` on an empty table and
has no caller yet (`backend/app/modules/srd/service.py:64`). `search_rules` calls it before embedding,
so an empty corpus costs no gateway request; the command catches `SrdError` → stderr + exit 1, the shape
`ingest` already uses (`backend/app/modules/srd/commands.py:120`).

**Tests can populate a corpus without real embeddings.** The `srd_db` fixture creates a scratch database,
pins `EMBEDDING_DIMENSIONS=1536` and runs the real migrations (`backend/tests/srd/conftest.py:105`).
Verified in Postgres: 1536-wide synthetic basis vectors order meaningfully — for rows `e0, e1, e2` and
query `0.9*e0 + 0.4*e1`, distances come back `0.086 / 0.594 / 1.0`. So ordering, `--limit` and the
empty-corpus path are all provable offline. Engine-free unit tests keep using the stub-session style
(`backend/tests/srd/test_service.py:33`) — note `tests/conftest.py` pins width 4 suite-wide, so anything
touching a real `VECTOR(1536)` column must use `srd_db` and the `database` marker.

## Measured retrieval quality (real embeddings, real corpus, top-5, score = 1 − distance)

- *"how does half cover work"* → **1. Combat › Cover (0.476)** — the correct passage. Ranks 2–5 are noise
  matching the word "half" (Half-Dragon Template 0.328, Uncanny Dodge 0.319, Jack of All Trades 0.315,
  Half-Elf Traits 0.307).
- *"what does the poisoned condition do"* → **1. … Conditions › … › Poisoned (0.549)**, then Swarm of
  Centipedes (0.525), Poisons ×3 (0.49–0.46). Good.
- *"how does grappling work"* → **1. Combat › Making an Attack › Melee Attacks › Grappling (0.634)**,
  then Grappler feat (0.559), Grappled condition (0.539). Best result of the four.
- *"what does fire bolt do"* → **the Fire Bolt passage is not in the top 5 — it ranks 47th (0.384)**.
  Top 5: Fire Elemental Actions (0.454), Fireball (0.448), Meteor Swarm (0.448), Red Dragon Wyrmling
  (0.441), Chain Lightning (0.440). Cause is verifiable: the embedded chunk text is the section *body*
  only — the passage's own name never appears in it, so every spell embeds as an interchangeable
  "Casting Time / Range / Components" block. Rephrased as *"fire bolt cantrip spell damage"* it rises to
  rank 6. Prepending `heading_path` to the embedded text would fix it, but that is a re-chunk plus a
  re-ingest, outside this sprint.
- Side observation: heading paths nest a sibling as a parent where the source skips a heading level —
  `Spell Lists › Spell Descriptions › Acid Arrow › Fire Bolt`, `Adventuring › Conditions › Blinded ›
  Poisoned`. The citation still identifies the right rule, but reads oddly. Pre-existing, from chunking.

## Work items

- **WI1 service**: `RuleMatch` in `schemas.py`, `DEFAULT_LIMIT` and `async search_rules` in `service.py`
  — guard, embed, one ordered+limited query, map rows to `RuleMatch`. Behaviours to test: best match
  first; `limit` caps the result and reaches the query (not sliced in Python); an empty corpus raises
  before `embed_texts` is called; no rows → `[]`; a `database`-marked test over synthetic 1536-wide
  vectors proving real ordering and the limit against the migrated table.
- **WI2 command + docs**: `app srd search "<query>"` in `commands.py`, `--limit`, and the `README.md`
  Surface entry. Behaviours to test: each match prints heading path, ordinal, score and text, best
  first; `--limit` is passed through and its absence leaves `DEFAULT_LIMIT` to the service; an empty
  corpus prints the empty-corpus message to stderr and exits 1 with nothing on stdout; a gateway
  failure prints one line and exits 1, never a traceback.

## Interfaces

```python
# backend/app/modules/srd/schemas.py
class RuleMatch(CamelModel):
    heading_path: str
    ordinal: int
    text: str
    score: float          # 1 - cosine distance; higher is better

# backend/app/modules/srd/service.py
DEFAULT_LIMIT = 5
async def search_rules(
    db: AsyncSession, query: str, *, limit: int = DEFAULT_LIMIT
) -> list[RuleMatch]: ...
```

WI2 imports `from app.modules.srd import service as srd_service` and calls
`srd_service.search_rules(db, query, limit=limit)`; it never issues a query itself (← D1). Command:
`app srd search QUERY [--limit N]`, exit 0 on results, exit 1 + stderr on `SrdError`/`LlmError`.

## Open questions

**Product-visible.**
- Asking for a spell by name can miss it: *"what does fire bolt do"* returns Fireball and Meteor Swarm,
  not Fire Bolt. Conditions and combat actions are reliable; named spells are not. Worth a follow-up
  backlog line (embed the heading with the passage, then re-ingest) before the DM agent relies on spell
  lookups.
- `DEFAULT_LIMIT = 5` is an assumption — five is where the observed noise starts anyway.

**Internal.**
- `score` as similarity (`1 - distance`) vs. raw distance: sprint 06 describes its floor as a
  cosine-distance threshold. Recommendation is similarity, with 06's floor expressed on the same scale.
