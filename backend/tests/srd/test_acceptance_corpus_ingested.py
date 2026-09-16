"""qa acceptance tests -- sprint 004/03 "corpus ingested" (AC1-AC5),
`docs/intents/004-srd-knowledge-base/sprints/03-corpus-ingested/brief.md`.

Black-box throughout: every test drives the real `app srd ingest` / `app srd
status` commands through `typer.testing.CliRunner` against `app.cli.cli`, or
the public `from app.modules.srd import service as srd_service` seam --
never a private helper, never the implementation modules themselves. The
network is never touched (`httpx.get` monkeypatched, mirroring sprint 04/02's
`test_acceptance_fetch_and_chunk.py`) and no real embedding call is ever made
(`app.core.llm.service.embed_texts` monkeypatched at the module level -- the
seam `ingest` calls attribute-style per the binding interface, so patching
`llm_service.embed_texts` reaches it regardless of how `srd/service.py`
imported the name, the same idiom `tests/core/llm/test_embeddings.py` uses
for `service.build_sdk_client`).

AC1/AC2/AC3/AC4 need real rows, so they use the `database`-marked `srd_db`
fixture (`tests/srd/conftest.py`, test infrastructure this file only
consumes) and carry `@pytest.mark.database`; the suite's global
`EMBEDDING_DIMENSIONS=4` pin is overridden to `1536` by that fixture for
their duration.

AC1's live run against a real `OPENROUTER_API_KEY` is a human/lead action
(plan.md's own assumption) with no automated equivalent; what is assertable
here, with the gateway faked, is everything about the command's own
contract -- it completes, exits 0, and prints all five figures of the
`IngestReport`. The live run itself is verified separately.

`app.core.db.get_engine`/`get_sessionmaker` are `@lru_cache`d for the whole
process (`app/core/db.py`) and are what the CLI's own commands use for a
database session (`app/modules/srd/commands.py`'s `status`, and per the
binding interface, `ingest`'s coming non-dry path) -- once either has been
called anywhere in this process it keeps returning the *same* engine,
regardless of what `DATABASE_URL` says afterwards. `_cli_uses_scratch_db()`
clears both caches immediately before and after every CLI invocation that
needs to reach `srd_db`'s scratch database, so each test's command runs
against its own fixture's database rather than a sibling test's -- already
torn down -- one.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.db import get_engine, get_sessionmaker
from app.core.errors import ErrorCode
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmRateLimitError
from app.core.settings import get_settings
from app.main import create_app
from app.modules.srd import service as srd_service

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# A small, fully-controlled fixture document -- three leaf sections with a
# real body each, never the ~1.9 MB real corpus. Mirrors sprint 04/02's own
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
    binding again afterwards so it never leaks into a sibling test once
    this scratch database is gone (module docstring). The engine the CLI
    built is disposed before the cache is cleared -- otherwise its pooled
    connection is only closed whenever the garbage collector gets to it,
    which pytest's unraisable-exception hook then blames on whatever test
    happens to be running at that later, unrelated moment."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    try:
        yield
    finally:
        asyncio.run(get_engine().dispose())
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


@pytest.mark.database
def test_ac1_real_ingest_completes_and_prints_the_full_ingest_report(srd_db, tmp_path, monkeypatch):
    # <- AC1: with the gateway faked (the live-key run is a human action,
    # verified separately), `app srd ingest` must still complete, exit 0,
    # and print every figure of the `IngestReport` -- source version,
    # bytes, chunk count, token count and USD cost.
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions, cost_usd=0.05))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code == 0, result.output

    expected_path = tmp_path / srd_service.SOURCE_VERSION / srd_service.SOURCE_FILENAME
    chunks = srd_service.chunk_source(expected_path)
    expected_chunk_count = len(chunks)
    expected_token_total = sum(chunk.token_count for chunk in chunks)

    assert srd_service.SOURCE_VERSION in result.stdout
    assert str(len(FIXTURE_MARKDOWN)) in result.stdout
    assert str(expected_chunk_count) in result.stdout
    assert str(expected_token_total) in result.stdout
    assert "0.05" in result.stdout


@pytest.mark.database
def test_ac2_status_immediately_after_ingest_reports_rules_model_and_time_and_exits_0(
    srd_db, tmp_path, monkeypatch
):
    # <- AC2: sprint 01 left `app srd status` exiting 1 on an empty corpus;
    # once a real ingest has populated it, the same command must report a
    # non-zero rule count, the embedding model used and when it ran, and
    # exit 0.
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))
    expected = asyncio.run(srd_service.corpus_status(srd_db))
    assert expected.rule_count > 0
    assert expected.ingested_at is not None

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "status"])

    assert result.exit_code == 0, result.output
    assert str(expected.rule_count) in result.stdout
    assert expected.embedding_model in result.stdout
    assert expected.ingested_at.date().isoformat() in result.stdout


@pytest.mark.database
def test_ac3_every_row_carries_its_fields_and_the_configured_vector_width(
    srd_db, tmp_path, monkeypatch
):
    # <- AC3
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions))

    asyncio.run(srd_service.ingest(srd_db))

    async def _read_rows():
        result = await srd_db.execute(
            text(
                "SELECT heading_path, ordinal, text, token_count, embedding_model, "
                "vector_dims(embedding) AS width FROM srd_rules"
            )
        )
        return result.all()

    rows = asyncio.run(_read_rows())
    assert rows, "ingest must write at least one row"

    expected_model = get_settings().embedding_model
    for row in rows:
        assert row.heading_path
        assert isinstance(row.ordinal, int)
        assert row.text
        assert row.token_count > 0
        assert row.embedding_model == expected_model
        assert row.width == dimensions


@pytest.mark.database
def test_ac4_a_gateway_failure_on_a_later_batch_leaves_no_rows_behind(
    srd_db, tmp_path, monkeypatch
):
    # <- AC4: the first batch must succeed before the failure -- otherwise
    # "half-filled" is never genuinely possible -- and once the gateway's
    # own error surfaces, the corpus must still be empty, not part-written.
    monkeypatch.setattr(srd_service, "SRD_ROOT", tmp_path)
    monkeypatch.setattr(httpx, "get", _fake_get(FIXTURE_MARKDOWN))
    monkeypatch.setattr(srd_service, "EMBED_BATCH_SIZE", 1)
    dimensions = get_settings().embedding_dimensions
    monkeypatch.setattr(llm_service, "embed_texts", _make_embed_texts(dimensions, fail_on_call=2))

    with _cli_uses_scratch_db():
        result = runner.invoke(cli, ["srd", "ingest"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert ErrorCode.LLM_RATE_LIMIT.value in result.stderr

    async def _count():
        count = await srd_db.execute(text("SELECT count(*) FROM srd_rules"))
        return count.scalar()

    assert asyncio.run(_count()) == 0


def test_ac5_nothing_outside_the_srd_module_touches_srd_rules_and_no_route_reaches_it():
    # <- AC5: grepping the real, unmocked tree -- never a fixture -- for
    # every reference to the model or the table name outside the module
    # that owns them, plus the real route table `create_app()` builds.
    backend_app_root = BACKEND_ROOT / "app"
    srd_module_root = backend_app_root / "modules" / "srd"

    offenders = []
    for path in backend_app_root.rglob("*.py"):
        if srd_module_root in path.parents:
            continue
        content = path.read_text()
        if "SrdRule" in content or "srd_rules" in content:
            offenders.append(str(path.relative_to(BACKEND_ROOT)))
    assert offenders == [], offenders

    application = create_app()
    srd_routes = [
        route.path for route in application.routes if "srd" in getattr(route, "path", "").lower()
    ]
    assert srd_routes == [], srd_routes
