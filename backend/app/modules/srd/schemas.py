from datetime import datetime

from app.core.schemas import CamelModel


class RuleChunk(CamelModel):
    """One citable passage carved out of the SRD source markdown by
    `service.chunk_source` -- the ingest-time shape `srd_rules` rows are
    built from (embedding is added later, sprint 03)."""

    heading_path: str
    ordinal: int
    text: str
    token_count: int


class CorpusStatus(CamelModel):
    """What is currently ingested. `rule_count == 0` is the empty case, in
    which the remaining fields carry no source to report and are `None`
    (`module-structure.md` §3)."""

    rule_count: int
    source_version: str | None
    embedding_model: str | None
    ingested_at: datetime | None


class RuleMatch(CamelModel):
    """One passage returned by `service.search_rules`: `heading_path`/
    `ordinal` are the same citation pair `RuleChunk` carries, identifying
    which stored `SrdRule` row this is. `score` is the raw pgvector cosine
    distance (`<=>`) between the query and the passage, 0..2, LOWER IS
    CLOSER -- not a similarity score. Results are ordered best-first
    (ascending distance); `service.search_rules` drops any row past
    `RELEVANCE_FLOOR` before returning (sprint 06)."""

    heading_path: str
    ordinal: int
    text: str
    score: float


class IngestReport(CamelModel):
    """What `service.ingest` did. `cost_usd` is `None` when no batch
    reported a cost; `cost_complete` is `False` when only some batches did
    (a known lower bound, not the true total)."""

    source_version: str
    source_bytes: int
    chunk_count: int
    token_count: int
    cost_usd: float | None
    cost_complete: bool = True
