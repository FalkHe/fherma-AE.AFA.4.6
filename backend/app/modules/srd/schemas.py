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
