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
  (`alembic/versions/0002_srd_rules.py`).
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
  with no headings) prints one stderr line and exits 1. Without
  `--dry-run` it prints one stderr line naming sprint 03 (embedding) and
  exits 1 -- there is nothing else to do yet. Embedding and retrieval are
  owned by later work items in this intent.

## Notes

- This work includes material taken from the System Reference Document 5.1
  ("SRD 5.1") by Wizards of the Coast LLC and available at
  https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
  is licensed under the Creative Commons Attribution 4.0 International
  License available at https://creativecommons.org/licenses/by/4.0/legalcode
  (D6).
- `srd_rules` is owned by nobody and replaced wholesale on re-ingest — no
  row-level ownership or partial update (`module-structure.md` §2).
