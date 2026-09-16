---
author: fhit:architect
owner: human
created: 2026-09-15
updated: 2026-09-15
stage: approved
---
# Attachment: SRD module structure (← D1–D7)

Names and shapes only. Naming follows `backend/app/modules/content/` and `…/users/`; the migration follows
`0001_baseline.py`. No `routes.py` and no wire schemas — there is no HTTP surface (← D1, D2).

## 1. Layout

| Path | Holds |
|---|---|
| `backend/app/modules/srd/service.py` | fetch, chunk, embed, ingest, search, status (← D1) |
| `backend/app/modules/srd/models.py` | `SrdRule` |
| `backend/app/modules/srd/schemas.py` | `RuleChunk`, `RuleMatch`, `CorpusStatus`, `IngestReport` |
| `backend/app/modules/srd/errors.py` | `SrdError`, `SrdSourceError`, `SrdCorpusEmptyError` |
| `backend/app/modules/srd/commands.py` | the `srd_app` Typer group (← D2) |
| `backend/app/modules/srd/README.md` · `__init__.py` | module doc (Owns / Surface / Notes, incl. CC-BY) · empty |
| `backend/alembic/versions/0002_srd_rules.py` | `vector` extension, `srd_rules` table, HNSW index |
| `backend/content/srd/v1/SRD_CC_v5.1.md` · `LICENSE.md` | fetched-and-stored source, committed (← D3) · CC-BY-4.0 + attribution (← D6) |
| `backend/tests/srd/` | mirrors the module, as every module |

## 2. Table — `srd_rules`

One citable SRD passage and its embedding; owned by nobody, replaced wholesale on re-ingest.

| Column | Type | Description |
|---|---|---|
| `id` | `ID_TYPE` PK | ULID, `default=generate_id` |
| `source_version` | `String` | the `v<n>` directory the passage came from |
| `heading_path` | `String` | ` › `-joined markdown heading chain — the citable reference (← D4) |
| `ordinal` | `Integer` | position of the passage inside its section |
| `text` | `Text` | the passage as embedded and as quoted |
| `token_count` | `Integer` | tokens in `text`, for ingest reporting |
| `embedding_model` | `String` | the model that produced `embedding` |
| `embedding` | `VECTOR(1536)` | HNSW index, `vector_cosine_ops` |
| `created_at` | `DateTime(tz)` | `server_default=func.now()` |

## 3. Schemas and errors

| Name | Fields / description |
|---|---|
| `RuleChunk` | `heading_path`, `ordinal`, `text`, `token_count` — one chunk before embedding |
| `RuleMatch` | `heading_path`, `ordinal`, `text`, `score` — one retrieved passage with its reference (← D4) |
| `CorpusStatus` | `rule_count`, `source_version`, `embedding_model`, `ingested_at` — `rule_count == 0` is the empty case (← D5) |
| `IngestReport` | `source_version`, `source_bytes`, `chunk_count`, `token_count`, `cost_usd` — what one run did |
| `SrdError` | base for every SRD failure |
| `SrdSourceError` | the source could not be fetched, stored or parsed |
| `SrdCorpusEmptyError` | the corpus holds no rules (← D5) |

## 4. Service functions

| Signature | Description |
|---|---|
| `SRD_ROOT: Path` | `backend/content/srd`, repointable in tests as `CONTENT_ROOT` is |
| `SOURCE_URL` · `SOURCE_VERSION` · `RELEVANCE_FLOOR` · `DEFAULT_LIMIT` | pinned module constants |
| `fetch_source(*, version=SOURCE_VERSION) -> Path` | download the CC-BY markdown, store it under `SRD_ROOT/<version>/`, return the stored path (← D3) |
| `chunk_source(path: Path) -> list[RuleChunk]` | split by heading, token-split oversized sections, carry `heading_path` + `ordinal` |
| `ingest(db: AsyncSession, *, version=SOURCE_VERSION) -> IngestReport` | fetch → store → chunk → embed → replace the corpus in one transaction (← D3) |
| `search_rules(db: AsyncSession, query: str, *, limit=DEFAULT_LIMIT) -> list[RuleMatch]` | embed the query, return matches above `RELEVANCE_FLOOR`, best first; `[]` means "no relevant rule" (← D7) |
| `corpus_status(db: AsyncSession) -> CorpusStatus` | what is currently ingested |
| `require_corpus(db: AsyncSession) -> None` | raise `SrdCorpusEmptyError` when empty — the guard playthrough creation calls (← D5) |

## 5. CLI commands

Wired in `backend/app/cli.py` as `cli.add_typer(srd_app, name="srd")`, beside `content` and `llm`.

| Command | Description |
|---|---|
| `app srd ingest` | fetch, store, embed; prints the `IngestReport` and the stored path |
| `app srd search "<query>"` | prints each `RuleMatch` — heading path, score, passage; prints "no relevant rule" on `[]` |
| `app srd status` | prints the `CorpusStatus`; exit 1 when the corpus is empty |

## 6. Call flow

```
app srd ingest ─► service.ingest ─► fetch_source ─► backend/content/srd/v1/*.md (reviewable diff)
                                 └► chunk_source ─► llm_service.embed_texts ─► srd_rules (replace)

phase-8 lookup_rule ─┐
app srd search ──────┴► service.search_rules ─► llm_service.embed_texts ─► srd_rules (cosine + floor)

phase-5 playthrough creation ─► service.require_corpus ─► SrdCorpusEmptyError
```

## 7. Stakeholders

| Who | Relationship |
|---|---|
| Phase 8 DM tool `lookup_rule(query)` (`docs/general/architecture.md:68`) | primary consumer of `search_rules` |
| Phase 5 playthrough creation path | calls `require_corpus` before the playthrough starts (← D5) |
| Operator running the CLI | runs `ingest` / `status`, reviews the stored-source diff |
| Phase 9/10 UI | later stage: displays the citation and the CC-BY attribution (← D4, D6) |
| Repository `README.md` | carries the attribution sentence in this phase (← D6) |

## 8. Interface with the outside

**Exposed** — via `from app.modules.srd import service as srd_service`: `search_rules`, `require_corpus`,
`corpus_status`, plus `RuleMatch` and `SrdCorpusEmptyError`; and the three `app srd …` commands. Nothing else
crosses the boundary; no caller touches `srd_rules` directly (← D1).

**Depended on** — `app.core.llm.service.embed_texts` (**not landed**: intent 001 backlog 04) ·
`app.core.db.Base` / `get_sessionmaker` · `app.core.ids.ID_TYPE` / `generate_id` · `app.core.settings`
(`embedding_model`, `embedding_dimensions`) · Postgres with the `vector` extension (`compose.yaml:76`) ·
the `pgvector` Python package · the CC-BY markdown at `SOURCE_URL`.
