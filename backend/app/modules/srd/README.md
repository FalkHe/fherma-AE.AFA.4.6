# srd

Owns the SRD 5.1 rules knowledge base — the citable passages and their
embeddings the DM agent retrieves rules from. Self-contained: nothing outside
this module reaches the corpus directly (D1).

## Owns

- The `srd_rules` table (`models.py`): one citable passage per row —
  `source_version`, `heading_path`, `ordinal`, `text`, `token_count`,
  `embedding_model`, `embedding` (`VECTOR(EMBEDDING_WIDTH)`, `EMBEDDING_WIDTH
  = 1536`) — indexed by `ix_srd_rules_embedding`, an HNSW `vector_cosine_ops`
  index for nearest-neighbour lookup.
- `SrdError` / `SrdCorpusEmptyError` / `SrdVectorWidthError` /
  `SrdSourceError` (`errors.py`).
- The `vector` extension and the `srd_rules` table/index migration
  (`alembic/versions/0002_srd_rules.py`), plus the `(source_version,
  heading_path, ordinal)` unique constraint
  (`alembic/versions/0009_srd_rules_unique_citation.py`) that keeps every
  citation addressable by exactly one row.
- The fetched SRD source markdown, `content/srd/<version>/SOURCE_FILENAME`
  (`SRD_ROOT`, `SOURCE_URL`, `SOURCE_VERSION`, `SOURCE_FILENAME` in
  `service.py`) and its `LICENSE.md` sibling, plus the chunking constants
  `MAX_CHUNK_TOKENS` / `CHUNK_OVERLAP_TOKENS`. A chunk's heading path closes
  its open heading stack by level, so a source that skips levels (e.g. `##`
  followed directly by `####`) still cites later siblings side by side
  instead of nesting them under the first one (sprint 004-07 WI1).

## Surface

- `app srd status` (`commands.py`): reports rule count, source version,
  embedding model and ingest time on stdout; exits 1 with a stderr line
  naming 0 rules and `app srd ingest` when the corpus is empty, or naming
  both widths on a vector-width mismatch.
- `app srd ingest --dry-run` (`commands.py`): reads the bundled
  SRD source and splits it into citable
  heading-path chunks (`service.chunk_source`), then reports the stored
  path, byte count, chunk count, total token count and a sample of heading
  paths on stdout. No DB access, no embedding call. `SrdSourceError` (an
  unreachable host, a non-2xx response, an unwritable target, or a source
  with no headings) prints one stderr line and exits 1.
- `app srd ingest` (`commands.py` / `service.ingest`):
  reads the bundled source, chunks, embeds (`core/llm/service.embed_texts`, batched under
  the gateway's per-request token cap by `EMBED_BATCH_SIZE`) and replaces
  the whole `srd_rules` table in one transaction, then reports the source
  version, byte count, chunk count, token count and USD cost (`n/a` when
  the gateway reported none, "(partial)" when only some batches were
  priced) on stdout. `SrdSourceError`, `SrdVectorWidthError` and an LLM
  gateway failure each print one stderr line and exit 1; a failure after
  the source file was replaced restores it to what it held before the
  call, and a failure during the write leaves the previous corpus
  untouched. Each chunk is embedded as `heading_path + "\n\n" + text` — the
  citation trail joined to the body — so a passage whose subject only
  appears in its heading (e.g. a spell's name) is still findable by that
  name; the stored `text` and `token_count` report the body alone, so the
  reported token count understates what was actually embedded by the
  heading trail's own length.
- `app srd search "<query>" [--limit N]` (`commands.py` / `service.search_rules`,
  sprint 004-05 WI1, sprint 004-06 WI1): embeds `query` through the shared
  gateway seam and returns up to `--limit` (default `DEFAULT_LIMIT = 5`)
  closest `srd_rules` passages at or below `RELEVANCE_FLOOR` (see
  "Relevance floor" below), best first, ordered by pgvector cosine
  distance. Prints one numbered block per match — citation, ordinal and
  raw distance on the heading line, the passage text indented below it. An
  empty result (every candidate past the floor) prints `no relevant rule`
  to stdout and exits 0 — a real, successful answer, not a failure.
  `SrdCorpusEmptyError` (checked before any gateway call) prints the same
  empty-corpus message as `status` to stderr and exits 1 — distinguishable
  from the no-relevant-rule case by both stream and exit code; a
  non-positive `--limit` is rejected before any call; `SrdVectorWidthError`
  or an LLM gateway failure prints one stderr line — each case exits 1 with
  no traceback. `RuleMatch.score` is the raw cosine distance (`<=>`), 0..2,
  lower is closer — not a similarity score.

Both ingestion modes use `content/srd/v1/SRD_CC_v5.1.md` by default. A missing
file fails with instructions to restore it or use `--refresh-source`; there
is no implicit download. Add `--refresh-source` to download and replace the
source first, including with `--dry-run`. Full ingestion restores the prior
source if subsequent processing fails; default local ingestion never rewrites it.

## Relevance floor

- `RELEVANCE_FLOOR = 0.60` (`service.py`) is a pinned module constant, not
  a setting — it carries no field on `Settings` and is never read from the
  environment, because it moves with the pinned embedding model
  (`EMBEDDING_MODEL`), not with a deployment; a model swap re-measures it.
  `score` is a cosine **distance** (lower is closer), so the floor is a
  **maximum**: a row with `distance > RELEVANCE_FLOOR` is dropped.
  `search_rules` applies it in Python, after the query is already ordered
  and `LIMIT`-applied, never as a SQL `WHERE` on the distance — a condition
  on the ordering expression itself would stop Postgres reaching for the
  `hnsw` index (`ix_srd_rules_embedding`) and fall back to a sequential
  scan plus sort, while filtering after the same ordered, limited query
  keeps the index scan. Consequence: `DEFAULT_LIMIT` (and any `--limit`)
  caps what a search *may* return, not a count of what it *will* — a
  past-the-floor row is dropped outright, so the result can be shorter
  than `limit`, including empty.
- **How 0.60 was chosen**: six in-corpus and five out-of-corpus questions,
  each measured with `docker compose run --rm app-cli app srd search
  "<query>" --limit 3` against the real ingested corpus
  (`openai/text-embedding-3-small`, 1,750 rules, each chunk embedded as
  its heading trail plus body). The worst in-corpus best-match distance
  was `0.515`; the best out-of-corpus best-match distance was `0.686` — no
  overlap, so `0.60` sits in the gap with a `0.085` margin on both sides.
  Re-measured on 2026-09-22 after the level-aware heading fix (sprint
  004-07) re-ingested the corpus with corrected citations: the same eleven
  questions gave the same worst in-corpus (`0.515`) and best out-of-corpus
  (`0.686`) distances, so the floor was left at `0.60`. The tables below
  are the re-measured values.

  In-corpus (every one the correct passage):

  | query | best distance | best match |
  |---|---|---|
  | how does half cover work | 0.515 | Combat › Cover |
  | what happens when a creature is frightened | 0.363 | Adventuring › Conditions › Frightened |
  | what does fire bolt do | 0.369 | Spell Lists › Spell Descriptions › Fire Bolt |
  | how does grappling work | 0.362 | Combat › Making an Attack › Melee Attacks › Grappling |
  | what is a saving throw | 0.297 | Using Ability Scores › Saving Throws |
  | how much does a longsword cost | 0.511 | Equipment › Weapons › Weapon Properties › Special Weapons |

  Out-of-corpus (none of these leak through; all print `no relevant rule`):

  | query | best distance | best match |
  |---|---|---|
  | how do I reload a plasma rifle | 0.686 | Equipment › Weapons › Weapon Properties › Special Weapons |
  | what is the capital of France | 0.857 | Classes › Bard › Spellcasting › Spellcasting Ability |
  | how do I file my taxes | 0.867 | Using Ability Scores › Saving Throws |
  | best pizza toppings | 0.813 | Spell Lists › Sorcerer Spells › 8th Level |
  | how to change a car tyre | 0.825 | Combat › Mounted Combat › Mounting and Dismounting |

## Notes

- This work includes material taken from the System Reference Document 5.1
  ("SRD 5.1") by Wizards of the Coast LLC and available at
  https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
  is licensed under the Creative Commons Attribution 4.0 International
  License available at https://creativecommons.org/licenses/by/4.0/legalcode
  (D6).
- `srd_rules` is owned by nobody and replaced wholesale on re-ingest — no
  row-level ownership or partial update (`module-structure.md` §2).
- Re-ingesting an unchanged source yields the same row count at a later
  ingest time; a changed source changes the file's byte diff and the row
  count together, since both derive from the same stored bytes (D3). A
  source whose chunking would produce two identical citations fails the
  write's unique constraint at commit and leaves the previous corpus
  untouched, rather than silently overwriting one citation with another.
