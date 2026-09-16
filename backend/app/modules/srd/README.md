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
- `SrdError` / `SrdCorpusEmptyError` / `SrdVectorWidthError` (`errors.py`).
- The `vector` extension and the `srd_rules` table/index migration
  (`alembic/versions/0002_srd_rules.py`).

## Surface

- Nothing yet — this work item lands the table shape only. Ingestion,
  embedding, retrieval and status live in `service.py` and the `app srd …`
  CLI, owned by later work items in this intent.

## Notes

- This work includes material taken from the System Reference Document 5.1
  ("SRD 5.1") by Wizards of the Coast LLC and available at
  https://dnd.wizards.com/resources/systems-reference-document. The SRD 5.1
  is licensed under the Creative Commons Attribution 4.0 International
  License available at https://creativecommons.org/licenses/by/4.0/legalcode
  (D6).
- `srd_rules` is owned by nobody and replaced wholesale on re-ingest — no
  row-level ownership or partial update (`module-structure.md` §2).
