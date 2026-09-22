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
  `MAX_CHUNK_TOKENS` / `CHUNK_OVERLAP_TOKENS`.

## Surface

- `app srd status` (`commands.py`): reports rule count, source version,
  embedding model and ingest time on stdout; exits 1 with a stderr line
  naming 0 rules and `app srd ingest` when the corpus is empty, or naming
  both widths on a vector-width mismatch.
- `app srd ingest --dry-run` (`commands.py`, sprint 004-02 WI1): fetches the
  SRD source (`service.fetch_source`) and splits it into citable
  heading-path chunks (`service.chunk_source`), then reports the stored
  path, byte count, chunk count, total token count and a sample of heading
  paths on stdout. No DB access, no embedding call. `SrdSourceError` (an
  unreachable host, a non-2xx response, an unwritable target, or a source
  with no headings) prints one stderr line and exits 1.
- `app srd ingest` (`commands.py` / `service.ingest`, sprint 004-03 WI1):
  fetches, chunks, embeds (`core/llm/service.embed_texts`, batched under
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
  sprint 004-05 WI1): embeds `query` through the shared gateway seam and
  returns up to `--limit` (default `DEFAULT_LIMIT = 5`) closest `srd_rules`
  passages, best first, ordered by pgvector cosine distance. Prints one
  numbered block per match — citation, ordinal and raw distance on the
  heading line, the passage text indented below it. `SrdCorpusEmptyError`
  (checked before any gateway call) prints the same empty-corpus message as
  `status`; a non-positive `--limit` is rejected before any call; any other
  `SrdError` or an LLM gateway failure prints one stderr line — each case
  exits 1 with no traceback. `RuleMatch.score` is the raw cosine distance
  (`<=>`), 0..2, lower is closer — not a similarity score; no relevance
  floor is applied yet (sprint 06).

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
