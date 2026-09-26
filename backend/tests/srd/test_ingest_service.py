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
from app.modules.srd.errors import SrdSourceError
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


def _stub_source(
    monkeypatch, tmp_path: Path, *, source_bytes: bytes = b"# Heading\n\nbody"
) -> Path:
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

    report = asyncio.run(srd_service.ingest(db, refresh_source=True))

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


@pytest.mark.parametrize("embedding_fails", [False, True])
def test_ingest_defaults_to_local_source_without_downloading_or_rewriting(
    matching_width, monkeypatch, tmp_path, embedding_fails
):
    path = _stub_source(monkeypatch, tmp_path)
    path.parent.mkdir(parents=True)
    original = b"# Local rules\n\nlocal body"
    path.write_bytes(original)
    original_mtime = path.stat().st_mtime_ns

    def forbidden_fetch(**kwargs):
        pytest.fail("default ingestion must not download")

    def embed(texts, *, model=None):
        assert texts == ["Local rules\n\nlocal body"]
        if embedding_fails:
            raise LlmError("embedding failed")
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=None),
        )

    monkeypatch.setattr(srd_service, "fetch_source", forbidden_fetch)
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", embed)
    db = FakeWriteSession()
    if embedding_fails:
        with pytest.raises(LlmError):
            asyncio.run(srd_service.ingest(db))
        assert db.executed == []
    else:
        asyncio.run(srd_service.ingest(db))
        assert db.committed
        assert db.added[0].text == "local body"
    assert path.read_bytes() == original
    assert path.stat().st_mtime_ns == original_mtime


def test_ingest_missing_local_source_fails_without_download(matching_width, monkeypatch, tmp_path):
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)

    def forbidden_fetch(**kwargs):
        pytest.fail("missing source must not trigger an implicit download")

    monkeypatch.setattr(srd_service, "fetch_source", forbidden_fetch)
    db = FakeWriteSession()
    with pytest.raises(SrdSourceError, match="--refresh-source"):
        asyncio.run(srd_service.ingest(db))
    assert db.executed == []


def test_ingest_embeds_the_heading_trail_joined_to_the_body_but_stores_the_body_alone(
    matching_width, monkeypatch, tmp_path
):
    # A spell's name lives only in `heading_path` (e.g. "... › Fire Bolt"),
    # never in its body text -- embedding the body alone makes every spell
    # interchangeable. `ingest` must embed `heading_path + body` while
    # `SrdRule.text`/`token_count` keep reporting the body only.
    dest_path = _stub_source(
        monkeypatch, tmp_path, source_bytes=b"# Fire Bolt\n\nRanged spell attack."
    )

    captured_texts: list[str] = []

    def fake_embed_texts(texts, *, model=None):
        captured_texts.extend(texts)
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", fake_embed_texts)
    db = FakeWriteSession()

    asyncio.run(srd_service.ingest(db, refresh_source=True))

    chunks = srd_service.chunk_source(dest_path)
    assert captured_texts == [f"{chunk.heading_path}\n\n{chunk.text}" for chunk in chunks]
    for row, chunk in zip(db.added, chunks, strict=True):
        assert row.text == chunk.text
        assert row.token_count == chunk.token_count


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
        asyncio.run(srd_service.ingest(db, refresh_source=True))

    assert db.added == []
    assert db.committed is False
    assert dest_path.read_bytes() == previous_bytes


def test_ingest_failing_on_the_second_batch_adds_and_commits_nothing(
    matching_width, monkeypatch, tmp_path
):
    # <- AC3: a batch failure "after some batches embedded" -- not just the
    # first and only one -- must still leave the write untouched. Two
    # headings (two chunks) with `EMBED_BATCH_SIZE` pinned to 1 forces two
    # separate `embed_texts` calls; the first succeeds, the second raises.
    monkeypatch.setattr(srd_service, "EMBED_BATCH_SIZE", 1)
    two_heading_source = b"# Heading One\n\nbody one\n\n# Heading Two\n\nbody two"
    dest_path = _stub_source(monkeypatch, tmp_path, source_bytes=two_heading_source)
    # `_stub_source` only points at the path; `fetch_source` writes it.
    assert not dest_path.exists()

    calls = {"count": 0}

    def flaky_embed_texts(texts, *, model=None):
        calls["count"] += 1
        if calls["count"] == 2:
            raise LlmError("second batch failed")
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", flaky_embed_texts)
    db = FakeWriteSession()

    with pytest.raises(LlmError):
        asyncio.run(srd_service.ingest(db, refresh_source=True))

    assert calls["count"] == 2
    assert db.executed == []
    assert db.added == []
    assert db.committed is False
    assert not dest_path.exists()  # restored to "no previous file"


def test_ingest_deletes_then_adds_then_commits_in_order_with_no_commit_before_delete(
    matching_width, monkeypatch, tmp_path
):
    # <- AC5: one transaction -- `delete(SrdRule)`, then `add_all`, then
    # exactly one `commit`, nothing committed before the delete.
    _stub_source(monkeypatch, tmp_path)

    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", fake_embed_texts)

    call_log: list[str] = []

    class OrderedFakeWriteSession(FakeWriteSession):
        async def execute(self, stmt):
            call_log.append("execute")
            assert self.committed is False
            await super().execute(stmt)

        def add_all(self, objs):
            call_log.append("add_all")
            assert self.committed is False
            super().add_all(objs)

        async def commit(self):
            call_log.append("commit")
            await super().commit()

    db = OrderedFakeWriteSession()

    asyncio.run(srd_service.ingest(db, refresh_source=True))

    assert call_log == ["execute", "add_all", "commit"]
    assert len(db.executed) == 1  # exactly one execute call: the delete


def test_ingest_row_count_follows_a_changed_source_file(matching_width, monkeypatch, tmp_path):
    # <- AC4: `chunk_source` is a pure function of the file bytes, so a
    # changed source (an added section) must yield a different chunk count,
    # and `ingest` writes exactly that many rows.
    dest_path = _stub_source(monkeypatch, tmp_path, source_bytes=b"# Heading One\n\nbody one")

    def fake_embed_texts(texts, *, model=None):
        return EmbeddingResult(
            vectors=[[0.1] * EMBEDDING_WIDTH for _ in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.01),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", fake_embed_texts)

    db_before = FakeWriteSession()
    report_before = asyncio.run(srd_service.ingest(db_before, refresh_source=True))
    original_chunks = srd_service.chunk_source(dest_path)
    assert report_before.chunk_count == len(original_chunks)
    assert len(db_before.added) == len(original_chunks)

    # `fetch_source` re-writes the file with an added section on the next call.
    def _fake_fetch_with_new_section(*, version=srd_service.SOURCE_VERSION):
        dest_path.write_bytes(b"# Heading One\n\nbody one\n\n# Heading Two\n\nbody two")
        return dest_path

    monkeypatch.setattr(srd_service, "fetch_source", _fake_fetch_with_new_section)

    db_after = FakeWriteSession()
    report_after = asyncio.run(srd_service.ingest(db_after, refresh_source=True))
    expected_chunks = srd_service.chunk_source(dest_path)

    assert report_after.chunk_count != report_before.chunk_count
    assert report_after.chunk_count == len(expected_chunks)
    assert len(db_after.added) == len(expected_chunks)
