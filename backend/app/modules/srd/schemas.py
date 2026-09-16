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


class IngestReport(CamelModel):
    """What one `app srd ingest` run did (or would do, under `--dry-run`):
    the source version fetched, how big the stored document is, how many
    citable `RuleChunk`s it split into and their combined token count.
    `cost_usd` is `None` when no embedding call was made at all -- always
    the case under `--dry-run`, since embedding is a later sprint (WI3) --
    or when a real ingest ran but the gateway priced none of its batches.
    Otherwise it is the sum of every batch's reported cost, whether or not
    every batch actually reported one: `cost_complete` is `False` when the
    gateway priced only some batches, so `cost_usd` is a known lower bound
    rather than the true total -- `True` (the default) covers both the
    fully-priced case and the no-embedding-call case, where there is
    nothing partial to flag."""

    source_version: str
    source_bytes: int
    chunk_count: int
    token_count: int
    cost_usd: float | None = None
    cost_complete: bool = True
