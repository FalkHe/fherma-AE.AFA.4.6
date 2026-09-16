"""qa acceptance tests -- sprint 004/01 "empty corpus status" (AC1-AC5),
`docs/intents/004-srd-knowledge-base/sprints/01-empty-corpus-status/brief.md`.

Black-box throughout: every test drives the real `app srd status` command
through `typer.testing.CliRunner` against `app.cli.cli`, the public
`from app.modules.srd import service as srd_service` seam, or the real
Postgres catalog -- never a private helper, never the implementation
modules themselves. AC1/AC2/AC4 are the live-database criteria and use the
`srd_db` fixture (`tests/srd/conftest.py`, a sibling work item's deliverable
this file only consumes); they carry `@pytest.mark.database` and skip
cleanly wherever no Postgres answers. AC3 is engine-free: `check_vector_width`
runs before any database access, so a mismatched `EMBEDDING_DIMENSIONS`
never needs a live server to be observed failing. AC5 checks the two halves
of its own claim that are assertable without reading the fixture's
internals: the `database` marker is registered (so using it never raises
under `filterwarnings=["error"]`), and the pre-existing, engine-free suite
still passes green when run for real.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas) -- every async call
is wrapped in a single `asyncio.run(...)` per test, never more than one, so
a fixture-provided `AsyncSession` is only ever driven from one event loop.
"""

import asyncio
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.ids import generate_id
from app.core.settings import get_settings
from app.modules.srd.errors import SrdCorpusEmptyError

runner = CliRunner()

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.database
def test_ac1_status_on_a_migrated_never_ingested_database_names_zero_rules_and_exits_1(srd_db):
    # <- AC1: after a real `alembic upgrade head` (the fixture's own setup),
    # a corpus nobody has ingested into reports 0 rules and fails loudly
    # rather than exiting 0 with nothing to show.
    result = runner.invoke(cli, ["srd", "status"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert "0" in result.stderr
    assert "rule" in result.stderr.lower()
    assert "ingest" in result.stderr.lower()


@pytest.mark.database
def test_ac2_migration_creates_the_extension_table_and_hnsw_cosine_index(srd_db):
    # <- AC2: asserted against the real database catalog, not model
    # metadata -- `vector` extension, `srd_rules`'s column set
    # (`decisions/module-structure.md` §2), and its HNSW `vector_cosine_ops`
    # index on `embedding`, exactly what an operator's `\d srd_rules` shows.
    async def _inspect():
        extension = await srd_db.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        )
        assert extension.scalar() == "vector"

        columns = await srd_db.execute(
            text(
                "SELECT column_name, data_type, udt_name, character_maximum_length "
                "FROM information_schema.columns WHERE table_name = 'srd_rules'"
            )
        )
        by_name = {row.column_name: row for row in columns}

        expected_columns = {
            "id",
            "source_version",
            "heading_path",
            "ordinal",
            "text",
            "token_count",
            "embedding_model",
            "embedding",
            "created_at",
        }
        assert expected_columns <= by_name.keys(), by_name.keys()

        assert by_name["id"].data_type == "character"
        assert by_name["id"].character_maximum_length == 26
        assert by_name["source_version"].data_type == "character varying"
        assert by_name["heading_path"].data_type == "character varying"
        assert by_name["ordinal"].data_type == "integer"
        assert by_name["text"].data_type == "text"
        assert by_name["token_count"].data_type == "integer"
        assert by_name["embedding_model"].data_type == "character varying"
        assert by_name["embedding"].udt_name == "vector"
        assert by_name["created_at"].data_type == "timestamp with time zone"

        indexes = await srd_db.execute(
            text("SELECT indexdef FROM pg_indexes WHERE tablename = 'srd_rules'")
        )
        index_defs = [row.indexdef for row in indexes]
        assert any(
            "ix_srd_rules_embedding" in d
            and "USING hnsw" in d
            and "vector_cosine_ops" in d
            and "embedding" in d
            for d in index_defs
        ), index_defs

    asyncio.run(_inspect())


def test_ac3_configured_vector_width_mismatch_exits_nonzero_naming_both_widths(monkeypatch):
    # <- AC3: `EMBEDDING_DIMENSIONS` set to anything but the migration's
    # 1536 must fail `app srd status` before any query -- `check_vector_width`
    # runs first, so this never needs a reachable database to prove.
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "3")
    get_settings.cache_clear()
    try:
        result = runner.invoke(cli, ["srd", "status"])
    finally:
        get_settings.cache_clear()

    assert result.exit_code != 0, result.output
    assert result.stdout == ""
    assert "3" in result.stderr
    assert "1536" in result.stderr


@pytest.mark.database
def test_ac4_require_corpus_raises_on_empty_and_returns_nothing_once_rows_exist(srd_db):
    # <- AC4: `srd_service.require_corpus()` -- the guard a later phase's
    # playthrough-creation path will call -- raises `SrdCorpusEmptyError` on
    # an empty corpus, and once a real row exists it returns `None` rather
    # than raising anything.
    from app.modules.srd import service as srd_service

    async def _scenario():
        with pytest.raises(SrdCorpusEmptyError):
            await srd_service.require_corpus(srd_db)

        await srd_db.execute(
            text(
                "INSERT INTO srd_rules "
                "(id, source_version, heading_path, ordinal, text, token_count, "
                "embedding_model, embedding) "
                "VALUES (:id, :source_version, :heading_path, :ordinal, :text, "
                ":token_count, :embedding_model, CAST(:embedding AS vector))"
            ),
            {
                "id": generate_id(),
                "source_version": "v1",
                "heading_path": "Combat › Actions",
                "ordinal": 0,
                "text": "On your turn, you can move and take one action.",
                "token_count": 11,
                "embedding_model": "test/embedding-model",
                "embedding": "[" + ",".join("0" for _ in range(1536)) + "]",
            },
        )
        await srd_db.commit()

        assert await srd_service.require_corpus(srd_db) is None

    asyncio.run(_scenario())


def test_ac5_database_marker_is_registered_and_the_existing_suite_stays_green():
    # <- AC5: the suite gains a DB-backed test path (AC1/AC2/AC4 above,
    # marked `database`) without breaking the offline default. What is
    # assertable here without reading the sibling fixture's internals:
    # the marker exists (so using it never raises `PytestUnknownMarkWarning`
    # under `filterwarnings=["error"]`), and the pre-existing, engine-free
    # suite still runs green for real when driven as a fresh process. The
    # marked tests' own clean skip with no reachable Postgres is this
    # fixture's documented contract, exercised live by AC1/AC2/AC4 whenever
    # a database *is* reachable, as here.
    pyproject = tomllib.loads((BACKEND_ROOT / "pyproject.toml").read_text())
    markers = pyproject.get("tool", {}).get("pytest", {}).get("ini_options", {}).get(
        "markers", []
    )
    assert any(marker.split(":")[0].strip() == "database" for marker in markers), markers

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests", "--ignore=tests/srd"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "failed" not in result.stdout.lower()
