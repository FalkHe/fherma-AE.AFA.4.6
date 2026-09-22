---
author: sprint
owner: agent
created: 2026-09-22
---
# Plan: Sprint 03 — corpus ingested

## Work items
| WI | Agent | Deliverable | Behaviours to test | Depends on |
|---|---|---|---|---|
| 1 | backend-python | `app srd ingest` embeds the stored SRD and fills `srd_rules` wholesale in one transaction, printing the `IngestReport` (version, bytes, chunks, tokens, USD cost); `app srd status` then reports rows, model and time; migration `0009` adds the unique citation constraint | with `embed_texts` monkeypatched: ingest writes one row per chunk carrying heading_path/ordinal/text/token_count/embedding_model and the report sums batch cost; an `LlmError` from a batch leaves no rows written and restores the previous stored source; the command prints the report and maps `LlmError`/`SrdSourceError`/`SrdVectorWidthError` to one stderr line + exit 1 | – |

Single WI, ported from `origin/sprint/004-03-corpus-ingested` (see research). No qa agent; the human asked for least effort and the live ingest is the proof.

## Interfaces
```python
# app/modules/srd/service.py
EMBED_BATCH_SIZE: int = 256
async def ingest(db: AsyncSession, *, version: str = SOURCE_VERSION,
                 on_batch: Callable[[int, int], None] | None = None) -> IngestReport: ...

# app/modules/srd/schemas.py
class IngestReport(CamelModel):
    source_version: str
    source_bytes: int
    chunk_count: int
    token_count: int
    cost_usd: float | None
    cost_complete: bool = True

# app/modules/srd/models.py — SrdRule gains
__table_args__ = (UniqueConstraint("source_version", "heading_path", "ordinal"),)
# alembic/versions/0009_srd_rules_unique_citation.py — revision "0009", down_revision "0008"
```
CLI: `app srd ingest` (no flag) opens a session via `get_sessionmaker`, calls `service.ingest`, prints the report; `--dry-run` keeps sprint 02's behaviour.

## Acceptance tests (qa)
None; AC1/AC2 by the live run recorded in `progress.md`, AC3/AC4 by WI1's unit tests, AC5 by inspection (no new caller outside the module).

## Order
WI1 alone.
