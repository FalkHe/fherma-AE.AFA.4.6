"""`service.ingest` -- embedding the stored corpus into `srd_rules` rows,
all-or-nothing on failure (AC3, AC4).

`llm_service.embed_texts` is the only network seam faked, monkeypatched as
a module attribute on `app.core.llm.service` (never a name import, per
`AGENTS.md`). `service.fetch_source` and `service.count_tokens` are also
monkeypatched so the test never touches the network or downloads
`tiktoken`'s BPE table. Engine-free: `db` is a bare stub recording
`execute`/`add_all`/`commit`/`rollback`, per `tests/srd/test_service.py`'s
`FakeScalarSession` precedent."""

import asyncio
from pathlib import Path

import pytest

from app.core.llm.errors import LlmError
from app.core.llm.service import EmbeddingResult, Usage
from app.core.settings import get_settings
from app.modules.srd import service as srd_service
from app.modules.srd.models import EMBEDDING_WIDTH


@pytest.fixture
def matching_width(monkeypatch):
    """Pins `EMBEDDING_DIMENSIONS` to `EMBEDDING_WIDTH` so
    `check_vector_width()` passes without a real, migrated database."""
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_WIDTH))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeWriteSession:
    """Stands in for `AsyncSession`: `ingest` only ever calls `execute`,
    `add_all`, `commit` and (on failure) `rollback`."""

    def __init__(self):
        self.executed: list[object] = []
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt):
        self.executed.append(stmt)

    def add_all(self, objs):
        self.added.extend(list(objs))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


def _stub_source(monkeypatch, tmp_path: Path, *, source_bytes: bytes = b"# Heading\n\nbody") -> Path:
    """Points `SRD_ROOT` at `tmp_path` (never the real committed corpus)
    and makes `fetch_source` write `source_bytes` there, exactly as the
    real one would -- so a failure path has a real file to restore."""
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)

    def _fake_fetch(*, version=srd_service.SOURCE_VERSION):
        dest_path = tmp_path / version / srd_service.SOURCE_FILENAME
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(source_bytes)
        return dest_path

    monkeypatch.setattr(srd_service, "fetch_source", _fake_fetch)
    monkeypatch.setattr(srd_service, "count_tokens", lambda text: len(text.split()))
    return tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME


def test_ingest_embeds_every_chunk_and_writes_one_row_each(matching_width, monkeypatch, tmp_path):
    dest_path = _stub_source(monkeypatch, tmp_path)

    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeWriteSession()

    report = asyncio.run(srd_service.ingest(db))

    chunks = srd_service.chunk_source(dest_path)
    assert len(db.added) == len(chunks)
    for row, chunk in zip(db.added, chunks, strict=True):
        assert row.heading_path == chunk.heading_path
        assert row.ordinal == chunk.ordinal
        assert row.text == chunk.text
        assert row.token_count == chunk.token_count
        assert row.embedding_model == get_settings().embedding_model
    assert len(db.executed) == 1  # the delete, issued before add_all
    assert db.committed is True
    assert report.chunk_count == len(chunks)
    assert report.cost_usd == pytest.approx(0.01)
    assert report.cost_complete is True


def test_ingest_on_embedding_failure_adds_and_commits_nothing_and_restores_the_source(
    matching_width, monkeypatch, tmp_path
):
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    dest_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    previous_bytes = b"# Old\n\nold body"
    dest_path.write_bytes(previous_bytes)

    def _fake_fetch(*, version=srd_service.SOURCE_VERSION):
        dest_path.write_bytes(b"# New\n\nnew body, fetched this call")
        return dest_path

    monkeypatch.setattr(srd_service, "fetch_source", _fake_fetch)
    monkeypatch.setattr(srd_service, "count_tokens", lambda text: len(text.split()))

    def failing_embed_texts(texts, *, model=None):
        raise LlmError("embedding failed")

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", failing_embed_texts)
    db = FakeWriteSession()

    with pytest.raises(LlmError):
        asyncio.run(srd_service.ingest(db))

    assert db.added == []
    assert db.committed is False
    assert dest_path.read_bytes() == previous_bytes
