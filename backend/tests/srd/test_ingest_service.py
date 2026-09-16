"""WI1: `service.ingest` -- embedding the stored corpus into `srd_rules`
rows, batched under the gateway's request cap, all-or-nothing on failure
(AC3, AC4).

`llm_service.embed_texts` is the only seam faked -- monkeypatched as a
module attribute on `app.core.llm.service` (never a name import, per
`service.ingest`'s own docstring), so the network is never touched, same
style as `tests/core/llm/test_service_helpers.py`. `service.fetch_source`
and `service.chunk_source` are monkeypatched too, for the tests that do not
care about the real ~1.9 MB corpus -- only `chunk_source`'s *output shape*
matters here, not its own parsing, which `test_acceptance_fetch_and_chunk.py`
already covers.

The suite-wide pin (`tests/conftest.py`) sets `EMBEDDING_DIMENSIONS=4`,
which never matches `SrdRule.EMBEDDING_WIDTH` (1536), so every engine-free
test below that needs `check_vector_width()` to pass sets
`EMBEDDING_DIMENSIONS` to 1536 itself via the local `matching_width`
fixture; the one test of the mismatch itself relies on the suite-wide pin
instead. Tests that need real rows (row contents, vector width, zero rows
after a failed batch) use the `database`-marked `srd_db` fixture
(`tests/srd/conftest.py`), which pins `EMBEDDING_DIMENSIONS=1536` itself.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
is wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.llm.service import EmbeddingResult, Usage
from app.core.settings import get_settings
from app.modules.srd import service as srd_service
from app.modules.srd.errors import SrdVectorWidthError
from app.modules.srd.models import EMBEDDING_WIDTH, SrdRule
from app.modules.srd.schemas import RuleChunk


@pytest.fixture
def matching_width(monkeypatch):
    """Pins `EMBEDDING_DIMENSIONS` to `EMBEDDING_WIDTH` for one engine-free
    test, so `check_vector_width()` passes without a real, migrated
    database -- mirrors `tests/srd/test_service.py`'s `embedding_width`."""
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", str(EMBEDDING_WIDTH))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeWriteSession:
    """Stands in for `AsyncSession` for the engine-free tests: `ingest`
    only ever calls `execute`, `add_all`, `commit` and (on failure)
    `rollback` on its `db`, so this records what happened without opening
    any real connection."""

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


def _chunks(n: int, *, tokens_each: int = 10) -> list[RuleChunk]:
    return [
        RuleChunk(heading_path=f"Section {i}", ordinal=0, text=f"body {i}", token_count=tokens_each)
        for i in range(n)
    ]


def _embed_result(n: int, *, cost_usd: float | None = 0.01) -> EmbeddingResult:
    return EmbeddingResult(
        vectors=[[0.0] * EMBEDDING_WIDTH for _ in range(n)],
        usage=Usage(prompt_tokens=n, completion_tokens=0, total_tokens=n, cost_usd=cost_usd),
    )


def _stub_fetch_and_chunk(
    monkeypatch, chunks: list[RuleChunk], path: Path = Path("/dev/null"), *, tmp_path: Path
):
    """Also repoints `SRD_ROOT` at an empty `tmp_path` (AGENTS.md: never
    touch the real ~1.9 MB committed source) -- `ingest` now reads whatever
    sits at `SRD_ROOT/<version>/SOURCE_FILENAME` before calling
    `fetch_source`, to know what to restore on a later failure (WI2), so a
    stubbed `fetch_source` must not leave that read pointed at the real
    stored copy."""
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(
        srd_service, "fetch_source", lambda *, version=srd_service.SOURCE_VERSION: path
    )
    monkeypatch.setattr(srd_service, "chunk_source", lambda p: chunks)


def _stub_fetch_writes(
    monkeypatch, tmp_path: Path, content: bytes, chunks: list[RuleChunk]
) -> Path:
    """Stands in for a `fetch_source` that actually replaced the stored
    file (unlike `_stub_fetch_and_chunk`'s, which never touches disk) --
    writes `content` to `SRD_ROOT/<version>/SOURCE_FILENAME` under
    `tmp_path` and returns that path, so `ingest`'s restore-on-failure path
    (WI2) has a real replaced file to restore. Returns the resulting
    `dest_path` for the caller's own assertions."""
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)

    def _fake_fetch(*, version=srd_service.SOURCE_VERSION):
        dest_path = tmp_path / version / srd_service.SOURCE_FILENAME
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(content)
        return dest_path

    monkeypatch.setattr(srd_service, "fetch_source", _fake_fetch)
    monkeypatch.setattr(srd_service, "chunk_source", lambda p: chunks)
    return tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME


def test_vector_width_mismatch_raises_before_any_gateway_call(monkeypatch):
    # Suite-wide pin leaves EMBEDDING_DIMENSIONS=4 != EMBEDDING_WIDTH=1536.
    calls: list[int] = []

    def _forbidden_fetch(*, version=srd_service.SOURCE_VERSION):
        raise AssertionError("fetch_source must not run when the vector width mismatches")

    def _forbidden_embed(texts, *, model=None):
        calls.append(len(texts))
        raise AssertionError("embed_texts must not be called when the vector width mismatches")

    monkeypatch.setattr(srd_service, "fetch_source", _forbidden_fetch)
    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _forbidden_embed)
    db = FakeWriteSession()

    with pytest.raises(SrdVectorWidthError):
        asyncio.run(srd_service.ingest(db))

    assert calls == []
    assert db.executed == []
    assert db.committed is False


def test_no_batch_exceeds_the_request_cap(matching_width, monkeypatch, tmp_path):
    total_chunks = srd_service.EMBED_BATCH_SIZE * 2 + 10
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)

    batch_sizes: list[int] = []

    def _fake_embed(texts, *, model=None):
        batch_sizes.append(len(texts))
        return _embed_result(len(texts))

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)
    db = FakeWriteSession()

    asyncio.run(srd_service.ingest(db))

    assert batch_sizes == [srd_service.EMBED_BATCH_SIZE, srd_service.EMBED_BATCH_SIZE, 10]
    assert all(size <= srd_service.EMBED_BATCH_SIZE for size in batch_sizes)
    assert sum(batch_sizes) == total_chunks
    assert len(db.added) == total_chunks


def test_on_batch_fires_after_each_batch_with_running_and_total_counts(
    matching_width, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 5
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)
    monkeypatch.setattr(
        srd_service.llm_service, "embed_texts", lambda texts, **_: _embed_result(len(texts))
    )
    db = FakeWriteSession()
    progress: list[tuple[int, int]] = []

    asyncio.run(srd_service.ingest(db, on_batch=lambda done, total: progress.append((done, total))))

    assert progress == [
        (srd_service.EMBED_BATCH_SIZE, total_chunks),
        (total_chunks, total_chunks),
    ]


def test_report_sums_tokens_and_the_costs_the_gateway_reported(
    matching_width, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 3
    chunks = _chunks(total_chunks, tokens_each=7)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)
    costs = iter([0.75, 0.10])

    def _fake_embed(texts, *, model=None):
        return _embed_result(len(texts), cost_usd=next(costs))

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)
    db = FakeWriteSession()

    report = asyncio.run(srd_service.ingest(db))

    assert report.token_count == total_chunks * 7
    assert report.chunk_count == total_chunks
    assert report.cost_usd == pytest.approx(0.85)
    assert report.cost_complete is True


def test_report_cost_is_the_partial_sum_and_flagged_incomplete_when_some_batches_priced(
    matching_width, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 3
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)
    costs = iter([0.75, None])

    def _fake_embed(texts, *, model=None):
        return _embed_result(len(texts), cost_usd=next(costs))

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)
    db = FakeWriteSession()

    report = asyncio.run(srd_service.ingest(db))

    assert report.cost_usd == pytest.approx(0.75)
    assert report.cost_complete is False


def test_report_cost_is_none_and_complete_when_no_batch_priced(
    matching_width, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 3
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)

    def _fake_embed(texts, *, model=None):
        return _embed_result(len(texts), cost_usd=None)

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)
    db = FakeWriteSession()

    report = asyncio.run(srd_service.ingest(db))

    assert report.cost_usd is None
    assert report.cost_complete is True


def test_a_failing_batch_writes_nothing_and_raises_before_any_db_call(
    matching_width, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 3
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)

    from app.core.llm.errors import LlmRateLimitError

    calls = {"n": 0}

    def _fake_embed(texts, *, model=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise LlmRateLimitError("rate limited")
        return _embed_result(len(texts))

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)
    db = FakeWriteSession()

    with pytest.raises(LlmRateLimitError):
        asyncio.run(srd_service.ingest(db))

    assert db.executed == []
    assert db.added == []
    assert db.committed is False


@pytest.mark.database
def test_ac3_rows_carry_every_field_chunk_order_and_a_full_width_vector(
    srd_db, monkeypatch, tmp_path
):
    chunks = [
        RuleChunk(heading_path="Combat › Cover", ordinal=0, text="half cover text", token_count=3),
        RuleChunk(
            heading_path="Combat › Cover", ordinal=1, text="three-quarters text", token_count=4
        ),
        RuleChunk(heading_path="Exploration › Traps", ordinal=0, text="trap text", token_count=2),
    ]
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)

    def _fake_embed(texts, *, model=None):
        # Each vector's first component encodes the input text's length, so
        # the test can recover which chunk a stored row's vector came from
        # without relying on any assumption about row/insert order.
        return EmbeddingResult(
            vectors=[[float(len(text))] * EMBEDDING_WIDTH for text in texts],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=0.05),
        )

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)

    report = asyncio.run(srd_service.ingest(srd_db))

    result = asyncio.run(srd_db.execute(select(SrdRule)))
    rows = {(row.heading_path, row.ordinal): row for row in result.scalars().all()}

    assert report.chunk_count == 3
    assert len(rows) == 3
    for chunk in chunks:
        row = rows[(chunk.heading_path, chunk.ordinal)]
        assert row.source_version == srd_service.SOURCE_VERSION
        assert row.text == chunk.text
        assert row.token_count == chunk.token_count
        assert row.embedding_model == get_settings().embedding_model
        assert len(row.embedding) == EMBEDDING_WIDTH
        # Vector traced back to the right chunk -- no shuffling between the
        # batched gateway call and the stored row (AC3).
        assert row.embedding[0] == pytest.approx(float(len(chunk.text)))


@pytest.mark.database
def test_ac4_a_failed_batch_leaves_the_corpus_empty_and_reraises_the_llm_error(
    srd_db, monkeypatch, tmp_path
):
    total_chunks = srd_service.EMBED_BATCH_SIZE + 3
    chunks = _chunks(total_chunks)
    _stub_fetch_and_chunk(monkeypatch, chunks, tmp_path=tmp_path)

    from app.core.llm.errors import LlmUnavailableError

    calls = {"n": 0}

    def _fake_embed(texts, *, model=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise LlmUnavailableError("gateway down")
        return _embed_result(len(texts))

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fake_embed)

    with pytest.raises(LlmUnavailableError):
        asyncio.run(srd_service.ingest(srd_db))

    count = asyncio.run(srd_db.scalar(select(func.count()).select_from(SrdRule)))
    assert count == 0


@pytest.mark.database
def test_ac3_ingest_replaces_the_corpus_wholesale(srd_db, monkeypatch, tmp_path):
    first_chunks = [RuleChunk(heading_path="Old", ordinal=0, text="stale", token_count=1)]
    _stub_fetch_and_chunk(monkeypatch, first_chunks, tmp_path=tmp_path)
    monkeypatch.setattr(
        srd_service.llm_service, "embed_texts", lambda texts, **_: _embed_result(len(texts))
    )
    asyncio.run(srd_service.ingest(srd_db))

    second_chunks = [RuleChunk(heading_path="New", ordinal=0, text="fresh", token_count=1)]
    _stub_fetch_and_chunk(monkeypatch, second_chunks, tmp_path=tmp_path)
    asyncio.run(srd_service.ingest(srd_db))

    result = asyncio.run(srd_db.execute(select(SrdRule)))
    rows = result.scalars().all()

    assert len(rows) == 1
    assert rows[0].heading_path == "New"


# WI2: a failed import restores the previously stored source file, so the
# repository and the corpus can never disagree (AC4).


def test_wi2_a_failure_after_replacing_the_file_restores_previous_bytes_and_corpus_untouched(
    matching_width, monkeypatch, tmp_path
):
    from app.core.llm.errors import LlmRateLimitError

    dest_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    dest_path.parent.mkdir(parents=True)
    old_content = b"# Old\n\nOld body.\n"
    dest_path.write_bytes(old_content)

    new_content = b"# New\n\nUpstream changed, but the embed below fails.\n"
    _stub_fetch_writes(monkeypatch, tmp_path, new_content, _chunks(3))

    def _fail_embed(texts, *, model=None):
        raise LlmRateLimitError("simulated failure mid-embed")

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fail_embed)
    db = FakeWriteSession()

    with pytest.raises(LlmRateLimitError):
        asyncio.run(srd_service.ingest(db))

    assert dest_path.read_bytes() == old_content
    assert db.executed == []
    assert db.committed is False


def test_wi2_a_successful_import_keeps_the_newly_stored_file(matching_width, monkeypatch, tmp_path):
    dest_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    dest_path.parent.mkdir(parents=True)
    dest_path.write_bytes(b"# Old\n\nOld body.\n")

    new_content = b"# New\n\nUpstream changed, and this import succeeds.\n"
    _stub_fetch_writes(monkeypatch, tmp_path, new_content, _chunks(2))
    monkeypatch.setattr(
        srd_service.llm_service, "embed_texts", lambda texts, **_: _embed_result(len(texts))
    )
    db = FakeWriteSession()

    asyncio.run(srd_service.ingest(db))

    assert dest_path.read_bytes() == new_content
    assert db.committed is True


def test_wi2_a_failure_with_no_previous_file_leaves_no_file_behind(
    matching_width, monkeypatch, tmp_path
):
    from app.core.llm.errors import LlmRateLimitError

    dest_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    assert not dest_path.exists()

    _stub_fetch_writes(monkeypatch, tmp_path, b"# New\n\nFirst-ever import.\n", _chunks(1))

    def _fail_embed(texts, *, model=None):
        raise LlmRateLimitError("simulated failure mid-embed")

    monkeypatch.setattr(srd_service.llm_service, "embed_texts", _fail_embed)
    db = FakeWriteSession()

    with pytest.raises(LlmRateLimitError):
        asyncio.run(srd_service.ingest(db))

    assert not dest_path.exists()
