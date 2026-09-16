"""qa acceptance tests -- sprint 004/04 "a second ingest replaces the
corpus" (AC1-AC5),
`docs/intents/004-srd-knowledge-base/sprints/04-reingest-replaces/brief.md`.

Black-box throughout: every test drives the real `app srd ingest` / `app
srd status` commands through `typer.testing.CliRunner` against `app.cli.cli`
or the public `from app.modules.srd import service as srd_service` seam --
never a private helper, never the implementation modules themselves, and
never a read of `service.py`/`models.py` while writing this file (per the
qa brief: these tests are written against the sprint brief and its
contracts, not the code). The network is never touched (`httpx.get`
monkeypatched) and no real embedding call is ever made
(`app.core.llm.service.embed_texts` monkeypatched at the module level),
mirroring sprint 04/03's `test_acceptance_corpus_ingested.py`.

Every criterion here needs a real, populated corpus, so every test uses the
`database`-marked `srd_db` fixture (`tests/srd/conftest.py`, test
infrastructure this file only consumes) and carries `@pytest.mark.database`;
that fixture overrides the suite's global `EMBEDDING_DIMENSIONS=4` pin to
`1536` for its duration.

`app.core.db.get_engine`/`get_sessionmaker` are `@lru_cache`d for the whole
process and are what the CLI's own commands use for a database session --
`_cli_uses_scratch_db()` clears both caches immediately before and after
every CLI invocation that needs to reach `srd_db`'s scratch database, exactly
as sprint 04/03's acceptance file does.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from typer.testing import CliRunner

from app.cli import cli
from app.core.db import get_engine, get_sessionmaker
from app.core.errors import ErrorCode
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmRateLimitError
from app.core.settings import get_settings
from app.modules.srd import service as srd_service

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# A small, fully-controlled fixture document -- three leaf sections with a
# real body each, never the ~1.9 MB real corpus. Mirrors sprint 04/03's own
# fixture shape.
FIXTURE_MARKDOWN = (
    b"# Combat\n\n"
    b"## Cover\n\n"
    b"### Half Cover\n\n"
    b"You have half cover if an obstacle blocks at least half of your body.\n\n"
    b"## Another Rule\n\n"
    b"Short filler text for another rule under combat.\n\n"
    b"# Exploration\n\n"
    b"## Traps\n\n"
    b"Simple filler text about traps in dungeons.\n"
)

# Two headings whose *text* differs only by a disambiguating anchor suffix
# -- upstream's own way of telling apart two entries that would otherwise
# share a heading -- so both collapse to the same heading trail
# ("Spells › Fire Bolt"). Per the brief, this is the exact collision AC2
# must survive: without per-trail numbering, both chunks would claim
# ordinal 0 under the same trail.
ANCHOR_COLLISION_MARKDOWN = (
    b"# Spells\n\n"
    b"## Fire Bolt {#fire-bolt}\n\n"
    b"A ranged spell attack that hurls a mote of fire at a creature or object.\n\n"
    b"## Fire Bolt {#fire-bolt-1}\n\n"
    b"A second, distinct entry upstream disambiguates with a numeric anchor "
    b"suffix, even though its heading text is otherwise identical to the one above.\n"
)


def _fake_get(body: bytes):
    """A stand-in for `httpx.get` returning a real `httpx.Response`, exactly
    `test_acceptance_fetch_and_chunk.py`'s helper."""

    def _get(url, *args, **kwargs):
        return httpx.Response(200, content=body, request=httpx.Request("GET", url))

    return _get


def _make_embed_texts(dimensions: int, *, fail_on_call: int | None = None, cost_usd: float = 0.05):
    """A stand-in for `llm_service.embed_texts` -- one call per batch. Every
    call before `fail_on_call` returns a real `EmbeddingResult` (vectors of
    the configured width, a priced `Usage`); the call numbered
    `fail_on_call` raises `LlmRateLimitError` instead, simulating a gateway
    failure on a batch that is not the first."""
    calls = {"n": 0}

    def _embed(texts, *, model=None):
        calls["n"] += 1
        if fail_on_call is not None and calls["n"] == fail_on_call:
            raise LlmRateLimitError("simulated rate limit mid-ingest")
        vectors = [[0.0] * dimensions for _ in texts]
        usage = llm_service.Usage(
            prompt_tokens=len(texts),
            completion_tokens=0,
            total_tokens=len(texts),
            cost_usd=cost_usd,
        )
        return llm_service.EmbeddingResult(vectors=vectors, usage=usage)

    return _embed


@contextmanager
def _cli_uses_scratch_db():
    """Force the CLI's cached `get_engine`/`get_sessionmaker` to rebuild
    against whichever `DATABASE_URL` `srd_db` just pinned, and drop that
    binding again afterwards -- exactly sprint 04/03's helper."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield
    finally:
        asyncio.run(get_engine().dispose())
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.database
def test_ac1_second_ingest_reports_the_same_rule_count_with_a_later_ingest_time(
    srd_db, tmp_path, monkeypatch
):
    # <- AC1
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))
    first = asyncio.run(srd_service.corpus_status(srd_db))
    assert first.rule_count > 0

    time.sleep(0.01)
    asyncio.run(srd_service.ingest(srd_db))
    second = asyncio.run(srd_service.corpus_status(srd_db))

    assert second.rule_count == first.rule_count
    assert second.ingested_at > first.ingested_at

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "status"])
    assert result.exit_code == 0, result.output
    assert str(second.rule_count) in result.stdout


@pytest.mark.database
def test_ac2_heading_path_and_ordinal_never_collide_even_across_anchor_collisions_and_repeated_runs(
    srd_db, tmp_path, monkeypatch
):
    # <- AC2
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(ANCHOR_COLLISION_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    # Run more than once -- the guarantee has to hold "after any number of
    # runs", not just the first.
    asyncio.run(srd_service.ingest(srd_db))
    asyncio.run(srd_service.ingest(srd_db))
    asyncio.run(srd_service.ingest(srd_db))

    async def _triples():
        result = await srd_db.execute(
            text("SELECT source_version, heading_path, ordinal FROM srd_rules")
        )
        return result.all()

    rows = asyncio.run(_triples())
    assert rows, "ingest must write at least one row"
    assert len(rows) == len(set(rows)), "duplicate (source_version, heading_path, ordinal) found"

    # Two of those rows must in fact share a heading trail (the anchor
    # collision this fixture exists to exercise) -- otherwise the test
    # proves nothing about the collision case at all.
    trails = [row.heading_path for row in rows]
    assert len(set(trails)) < len(trails), "fixture did not produce a colliding heading trail"

    # The guarantee must not rest on the splitter alone: the database
    # itself refuses a duplicate (source_version, heading_path, ordinal)
    # triple, independent of whatever the application code does.
    async def _insert_duplicate():
        await srd_db.execute(
            text(
                "INSERT INTO srd_rules "
                "(source_version, heading_path, ordinal, text, token_count, "
                "embedding_model, embedding) "
                "SELECT source_version, heading_path, ordinal, text, token_count, "
                "embedding_model, embedding FROM srd_rules LIMIT 1"
            )
        )
        await srd_db.commit()

    with pytest.raises(IntegrityError):
        asyncio.run(_insert_duplicate())
    asyncio.run(srd_db.rollback())


@pytest.mark.database
def test_ac3_a_failed_reingest_leaves_the_earlier_populated_corpus_intact(
    srd_db, tmp_path, monkeypatch
):
    # <- AC3
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))
    before = asyncio.run(srd_service.corpus_status(srd_db))
    assert before.rule_count > 0

    monkeypatch.setattr(srd_service, "EMBED_BATCH_SIZE", 1)
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions, fail_on_call=2))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "ingest"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert ErrorCode.LLM_RATE_LIMIT.value in result.stderr

    after = asyncio.run(srd_service.corpus_status(srd_db))
    assert after.rule_count == before.rule_count
    assert after.ingested_at == before.ingested_at


@pytest.mark.database
def test_ac4_reingest_of_changed_source_moves_file_and_corpus_together_and_failure_moves_neither(
    srd_db, tmp_path, monkeypatch
):
    # <- AC4
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))
    before_status = asyncio.run(srd_service.corpus_status(srd_db))
    stored_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    assert stored_path.read_bytes() == FIXTURE_MARKDOWN

    changed_markdown = (
        FIXTURE_MARKDOWN + b"\n## A New Rule\n\nSomething upstream added, a changed chunk count.\n"
    )
    monkeypatch.setattr(httpx, "get", _fake_get(changed_markdown))

    # Successful re-ingest of a changed source: the stored file and the
    # corpus move together.
    asyncio.run(srd_service.ingest(srd_db))
    after_success_status = asyncio.run(srd_service.corpus_status(srd_db))
    assert stored_path.read_bytes() == changed_markdown
    assert after_success_status.rule_count != before_status.rule_count

    # A further upstream change, this time failing partway through
    # embedding: the stored file must be restored byte-for-byte to what it
    # was before this attempt, and the corpus must stay exactly as the
    # last successful import left it.
    further_changed_markdown = (
        changed_markdown + b"\n## Yet Another Rule\n\nMore text upstream added on a later run.\n"
    )
    monkeypatch.setattr(httpx, "get", _fake_get(further_changed_markdown))
    monkeypatch.setattr(srd_service, "EMBED_BATCH_SIZE", 1)
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions, fail_on_call=2))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "ingest"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output

    after_failure_status = asyncio.run(srd_service.corpus_status(srd_db))
    assert stored_path.read_bytes() == changed_markdown
    assert after_failure_status.rule_count == after_success_status.rule_count
    assert after_failure_status.ingested_at == after_success_status.ingested_at


@pytest.mark.database
def test_ac5_no_reader_ever_observes_a_partially_replaced_corpus(srd_db, tmp_path, monkeypatch):
    # <- AC5
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))
    before = asyncio.run(srd_service.corpus_status(srd_db))
    assert before.rule_count > 0

    changed_markdown = (
        FIXTURE_MARKDOWN
        + b"\n## A New Rule\n\nSomething new, giving the second import a different chunk count.\n"
    )
    monkeypatch.setattr(httpx, "get", _fake_get(changed_markdown))
    monkeypatch.setattr(srd_service, "EMBED_BATCH_SIZE", 1)

    def _slow_embed(texts, *, model=None):
        # Widen the window a concurrent reader has to catch a partial state
        # in, without ever touching the network or a real embedding call.
        time.sleep(0.05)
        return _make_embed_texts(dimensions)(texts, model=model)

    monkeypatch.setattr(llm_service, "embed_texts", _slow_embed)

    # A reader independent of the ingest's own session/connection: a plain,
    # separate connection to the same scratch database, polled from another
    # thread for the whole duration of the (slowed-down) ingest.
    observed_counts: set[int] = set()
    stop = threading.Event()
    poll_engine = create_engine(os.environ["DATABASE_URL"])

    def _poll():
        while not stop.is_set():
            with poll_engine.connect() as conn:
                observed_counts.add(conn.execute(text("SELECT count(*) FROM srd_rules")).scalar())
            time.sleep(0.005)

    poller = threading.Thread(target=_poll)
    poller.start()
    try:
        asyncio.run(srd_service.ingest(srd_db))
    finally:
        stop.set()
        poller.join()
        poll_engine.dispose()

    after = asyncio.run(srd_service.corpus_status(srd_db))
    assert after.rule_count != before.rule_count
    assert observed_counts, "the poller never managed a single read"
    assert observed_counts <= {before.rule_count, after.rule_count}, (
        f"an intermediate row count was observed: {observed_counts}"
    )
