"""qa acceptance tests -- sprint 004/04 "re-ingest replaces" (AC1-AC5),
`docs/intents/004-srd-knowledge-base/sprints/04-reingest-replaces/research.md`.

`service.ingest` already implements every criterion (sprint 03); this file
is the proof against a real, migrated database rather than the engine-free
`FakeWriteSession` stand-in `test_ingest_service.py` uses -- the unique
constraint, the server-side `created_at` default and the one-transaction
delete/insert/commit only exist to be violated or honoured on a real
Postgres session. `@pytest.mark.database`, over the `srd_db` fixture
(`tests/srd/conftest.py`); skips cleanly wherever no Postgres answers, per
`make backend-test`'s `-m "not database"` default.

`embed_texts` is stubbed to deterministic vectors (no gateway call, no
cost) and `count_tokens` to a cheap word-count stand-in, per
`test_ingest_service.py`'s precedent -- this suite must never touch the
network or trigger tiktoken's BPE download."""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from app.core.llm.service import EmbeddingResult, Usage
from app.modules.srd import service as srd_service
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule


def _stub_source(monkeypatch, tmp_path: Path, *, source_bytes: bytes) -> Path:
    """Same seam as `test_ingest_service.py`'s helper: points `SRD_ROOT` at
    `tmp_path` and makes `fetch_source` write `source_bytes` there."""
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)

    def _fake_fetch(*, version=srd_service.SOURCE_VERSION):
        dest_path = tmp_path / version / srd_service.SOURCE_FILENAME
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(source_bytes)
        return dest_path

    monkeypatch.setattr(srd_service, "fetch_source", _fake_fetch)
    monkeypatch.setattr(srd_service, "count_tokens", lambda text: len(text.split()))
    return tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME


def _fake_embed_texts(texts, *, model=None):
    return EmbeddingResult(
        vectors=[[0.0] * EMBEDDING_WIDTH for _ in texts],
        usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.0),
    )


@pytest.mark.database
def test_reingest_replaces_the_corpus_and_a_duplicate_citation_leaves_it_intact(
    srd_db, monkeypatch, tmp_path
):
    two_heading_source = b"# Heading One\n\nbody one\n\n# Heading Two\n\nbody two"
    dest_path = _stub_source(monkeypatch, tmp_path, source_bytes=two_heading_source)
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed_texts)

    async def _row_count_and_distinct_citations():
        total = await srd_db.scalar(select(func.count()).select_from(SrdRule))
        distinct = await srd_db.scalar(
            select(func.count(func.distinct(SrdRule.heading_path, SrdRule.ordinal)))
        )
        return total, distinct

    async def _max_created_at():
        return await srd_db.scalar(select(func.max(SrdRule.created_at)))

    try:
        # First ingest.
        report_one = asyncio.run(srd_service.ingest(srd_db))
        count_one, distinct_one = asyncio.run(_row_count_and_distinct_citations())
        created_at_one = asyncio.run(_max_created_at())

        assert count_one == report_one.chunk_count
        assert count_one == distinct_one  # AC2: no citation stored twice

        # Second ingest, same source -- AC1: same row count, later ingest time.
        report_two = asyncio.run(srd_service.ingest(srd_db))
        count_two, distinct_two = asyncio.run(_row_count_and_distinct_citations())
        created_at_two = asyncio.run(_max_created_at())

        assert count_two == count_one == report_two.chunk_count
        assert count_two == distinct_two
        assert created_at_two > created_at_one

        # Third ingest, chunks carry a duplicated citation -- AC3/AC5: the
        # commit raises on the unique constraint, and the second corpus
        # (its count and ingest time) is left untouched.
        duplicate_chunks = srd_service.chunk_source(dest_path)
        duplicate_chunks.append(duplicate_chunks[0])
        monkeypatch.setattr(srd_service, "chunk_source", lambda path: duplicate_chunks)

        with pytest.raises(Exception):  # noqa: B017 - the DB driver's own IntegrityError type
            asyncio.run(srd_service.ingest(srd_db))

        # A failed commit leaves the session with a pending rollback; a
        # fresh statement needs it rolled back first, exactly like any
        # other caller resuming after `ingest` re-raises.
        asyncio.run(srd_db.rollback())

        count_three, distinct_three = asyncio.run(_row_count_and_distinct_citations())
        created_at_three = asyncio.run(_max_created_at())

        assert count_three == count_two
        assert distinct_three == distinct_two
        assert created_at_three == created_at_two
    finally:
        asyncio.run(srd_db.execute(text("DELETE FROM srd_rules")))
        asyncio.run(srd_db.commit())
