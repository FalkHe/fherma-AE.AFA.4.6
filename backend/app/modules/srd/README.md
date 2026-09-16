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
- `RuleChunk` / `IngestReport` (`schemas.py`): a `RuleChunk` is one citable
  passage `service.chunk_source` produced — `heading_path`, `ordinal`,
  `text`, `token_count`; an `IngestReport` is what one `app srd ingest` run
  did or would do — source version, stored byte count, chunk count, total
  token count and `cost_usd` (`None` under `--dry-run`, no embedding call).
- `SrdError` / `SrdCorpusEmptyError` / `SrdVectorWidthError` / `SrdSourceError`
  (`errors.py`).
- The `vector` extension and the `srd_rules` table/index migration
  (`alembic/versions/0002_srd_rules.py`).

## Surface

- `app srd status` (`commands.py`): reports rule count, source version,
  embedding model and ingest time on stdout; exits 1 with a stderr line
  naming 0 rules and `app srd ingest` when the corpus is empty, or naming
  both widths on a vector-width mismatch.
- `app srd ingest --dry-run` (`commands.py`): fetches the source document,
  stores it and splits it into citable chunks, then prints the stored
  path, byte count, chunk count, total token count and a sample of heading
  paths — fetch + store + chunk only, no database and no embedding call.
- `app srd ingest` (no flag, `commands.py`): runs `service.ingest` for
  real — one progress line per embed batch, then the report (source
  version, bytes, chunk count, token count, cost). A gateway failure
  (`LlmError`) or a source/vector-width failure (`SrdError`) prints one
  stderr line and exits 1, never a traceback; searching is a later work
  item in this intent.
- `service.ingest(db, *, version, on_batch)` (`service.py`): fetches,
  stores, chunks, embeds in `EMBED_BATCH_SIZE`-sized batches and replaces
  `srd_rules` wholesale in one transaction opened only after every vector
  is in hand; `on_batch(chunks_done, chunks_total)` fires after each batch
  for a caller's progress reporting — the service itself never prints.
- `service.fetch_source()` downloads `SOURCE_URL` and stores it at
  `SRD_ROOT/<version>/SOURCE_FILENAME`, overwriting an existing copy in
  place; a non-200 response, a timeout/connection failure or an empty body
  raise `SrdSourceError` and leave a previously stored file untouched (the
  download lands in a temporary file first, then is moved into place).
- `service.count_tokens(text)` / `service.chunk_source(path)`: splits a
  stored document into one `RuleChunk` per heading section, further
  splitting an oversized section on token boundaries with overlap so a
  citation at a split still reads in context (`MAX_CHUNK_TOKENS`,
  `CHUNK_OVERLAP_TOKENS`); a heading with no body text yields no chunk.
- `backend/content/srd/v1/` vendors the rules source (`SRD_CC_v5.1.md`) and
  its licence (`LICENSE.md`) that `fetch_source`/`chunk_source` read.

## Notes

- This work includes material taken from the System Reference Document 5.1
  ("SRD 5.1") by Wizards of the Coast LLC and available at
  https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
  is licensed under the Creative Commons Attribution 4.0 International
  License available at https://creativecommons.org/licenses/by/4.0/legalcode
  (D6).
- `srd_rules` is owned by nobody and replaced wholesale on re-ingest — no
  row-level ownership or partial update (`module-structure.md` §2).
