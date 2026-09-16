from datetime import datetime

from app.core.schemas import CamelModel


class CorpusStatus(CamelModel):
    """What is currently ingested. `rule_count == 0` is the empty case, in
    which the remaining fields carry no source to report and are `None`
    (`module-structure.md` §3)."""

    rule_count: int
    source_version: str | None
    embedding_model: str | None
    ingested_at: datetime | None


class RuleChunk(CamelModel):
    """One citable passage produced by `service.chunk_source` (AC2, AC4):
    `heading_path` is the ` › `-joined trail of headings the passage sits
    under, with any `{#anchor}` suffix stripped; `ordinal` is its position
    (from 0) among the passages of the same section, ascending when a
    section had to be split; `token_count` is `service.count_tokens(text)`."""

    heading_path: str
    ordinal: int
    text: str
    token_count: int
