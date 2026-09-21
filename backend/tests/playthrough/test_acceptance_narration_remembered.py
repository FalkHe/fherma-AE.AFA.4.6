"""qa acceptance tests -- sprint 006/01 "narration is remembered on write"
(`docs/intents/006-journal-memory/sprints/01-narration-remembered-on-write
/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`,
`.models` or `.commands` themselves -- those are this sprint's own work
items, written in parallel, and this file never reads them.

AC1 carries `@pytest.mark.database`: every assertion is a real Postgres
read, over the shared `playthrough_db` fixture (`tests/playthrough
/conftest.py`), which already runs `alembic upgrade head` -- so the scratch
database is on `0008` before this file's own scenario runs. Columns,
nullability and the partial index are read from `information_schema` /
`pg_indexes`, never from the migration source; "touches nothing 0007
changes" is proven by re-exercising two of 0007's own checks (the
`events.type` CHECK and `campaign_runs.status`'s default) after the
upgrade, exactly as `test_acceptance_migration_0007.py` proves them for
`0007` itself.

AC2-AC4 drive `append_event` directly (I2), engine-free: a duck-typed
`_RecordingSession` stand-in needing only `add` (sync) and `flush`
(async) -- precedent: `test_acceptance_transcript_writer_and_read.py`'s own
`_RecordingSession`. The one seam this sprint adds, `embed_texts`, is
monkeypatched on the actual module the interface names --
`app.core.llm.service` -- never on whatever alias
`app.modules.playthrough.service` imports it under, so this file never has
to know that alias exists (I2: "a module attribute -- llm_service
.embed_texts([text]) where llm_service is app.core.llm.service").

Every fake encoder answers exactly 1536 floats (the playthrough module's
own `EMBEDDING_WIDTH`, fixed by the sprint's own interface contract, never
imported from `models.py`): the suite-wide `EMBEDDING_DIMENSIONS` pin is
`4` (`tests/conftest.py`), a width that belongs to a different module
entirely and would make every stored-vector assertion below pass by
accident if it were used here instead.

AC5 drives the real `cli` through `CliRunner`, with only
`playthrough_service.append_event` monkeypatched -- `tests/srd
/test_commands.py`'s style, also used by this suite's own
`test_acceptance_cost_and_live_signal.py`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas); every async call
outside the CLI scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
models or command themselves -- this suite is red until the corresponding
work items land, and green once they do.
"""

import asyncio

import pytest
import structlog.testing
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from typer.testing import CliRunner

from app.cli import cli
from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmConfigurationError
from app.core.llm.service import EmbeddingResult, Usage
from app.core.settings import get_settings
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError

runner = CliRunner()

EMBEDDING_WIDTH = 1536  # fixed by the sprint's own interface contract (I1)


def _vector(value: float = 0.25, width: int = EMBEDDING_WIDTH) -> list[float]:
    return [value] * width


class _RecordingSession:
    """Engine-free stand-in for the `AsyncSession` `append_event` is
    handed -- the sprint's own interface (I2) asks nothing of `db` beyond
    `add` (sync) and `flush` (async), same as `test_acceptance_transcript
    _writer_and_read.py`'s own `_RecordingSession`."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


# --- AC1 -- migration 0008 -------------------------------------------------


@pytest.mark.database
def test_ac1_migration_0008_adds_the_columns_and_index_and_touches_nothing_0007_owns(
    playthrough_db,
):
    # <- AC1
    async def _scenario():
        version_row = await playthrough_db.execute(text("SELECT version_num FROM alembic_version"))
        assert version_row.scalar() == "0008"

        columns = (
            await playthrough_db.execute(
                text(
                    "SELECT column_name, is_nullable, udt_name FROM information_schema.columns "
                    "WHERE table_name = 'events' AND column_name IN "
                    "('embedding', 'embedding_model')"
                )
            )
        ).all()
        by_name = {row.column_name: row for row in columns}
        assert set(by_name) == {"embedding", "embedding_model"}
        assert by_name["embedding"].is_nullable == "YES"
        assert by_name["embedding"].udt_name == "vector"
        assert by_name["embedding_model"].is_nullable == "YES"

        index_row = (
            await playthrough_db.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname = "
                    "'ix_events_embedding_narration'"
                )
            )
        ).first()
        assert index_row is not None, "ix_events_embedding_narration does not exist"
        indexdef = index_row.indexdef.lower()
        assert "hnsw" in indexdef
        assert "vector_cosine_ops" in indexdef
        assert "'narration'" in indexdef
        assert "embedding is not null" in indexdef

        # A write-then-read round trip: a narration row carrying a real
        # 1536-wide vector and a model name reads back unchanged; a row
        # with neither reads back as NULL on both columns.
        run_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO campaign_runs (id, campaign_id, content_version) "
                "VALUES (:id, 'greenhollow', 'v1')"
            ),
            {"id": run_id},
        )
        await playthrough_db.commit()

        vector = _vector()
        vector_literal = "[" + ",".join(str(v) for v in vector) + "]"
        embedded_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload, "
                "embedding, embedding_model) VALUES (:id, :run_id, 'narration', 'player', "
                "'{}'::jsonb, CAST(:embedding AS vector), :model)"
            ),
            {"id": embedded_id, "run_id": run_id, "embedding": vector_literal, "model": "test/m"},
        )
        bare_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                "VALUES (:id, :run_id, 'narration', 'player', '{}'::jsonb)"
            ),
            {"id": bare_id, "run_id": run_id},
        )
        await playthrough_db.commit()

        read_back = (
            await playthrough_db.execute(
                text(
                    "SELECT id, embedding::text AS embedding_text, embedding_model "
                    "FROM events WHERE id IN (:a, :b)"
                ),
                {"a": embedded_id, "b": bare_id},
            )
        ).all()
        by_id = {row.id: row for row in read_back}
        stored_vector = [float(v) for v in by_id[embedded_id].embedding_text.strip("[]").split(",")]
        assert len(stored_vector) == EMBEDDING_WIDTH
        assert stored_vector == pytest.approx(vector)
        assert by_id[embedded_id].embedding_model == "test/m"
        assert by_id[bare_id].embedding_text is None
        assert by_id[bare_id].embedding_model is None

        # Nothing 0007 owns is touched: its `events.type` CHECK still
        # refuses an unknown kind, and `campaign_runs.status` still
        # defaults to `setup` -- both proven the same way `test_acceptance
        # _migration_0007.py` proves them for `0007` itself.
        with pytest.raises((IntegrityError, DBAPIError)) as exc_info:
            await playthrough_db.execute(
                text(
                    "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                    "VALUES (:id, :run_id, 'monologue', 'player', '{}'::jsonb)"
                ),
                {"id": generate_id(), "run_id": run_id},
            )
            await playthrough_db.commit()
        await playthrough_db.rollback()
        assert "ck_events_type" in str(exc_info.value)

        default_status = (
            await playthrough_db.execute(
                text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": run_id}
            )
        ).first()
        assert default_status.status == "setup"

    asyncio.run(_scenario())


# --- AC2 -- narration is embedded and billed --------------------------------


def test_ac2_narration_stores_its_vector_and_model_and_adds_the_embeddings_tokens_and_cost():
    # <- AC2
    def fake_embed_texts(texts, *, model=None):
        assert list(texts) == ["The tavern falls silent as you enter."]
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=8, completion_tokens=0, total_tokens=8, cost_usd=0.25),
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(llm_service, "embed_texts", fake_embed_texts)
        db = _RecordingSession()
        caller_usage = Usage(
            prompt_tokens=100, completion_tokens=40, total_tokens=140, cost_usd=0.5
        )

        event = asyncio.run(
            playthrough_service.append_event(
                db,
                run_id=generate_id(),
                type="narration",
                visibility="player",
                payload={"text": "The tavern falls silent as you enter."},
                usage=caller_usage,
            )
        )

    assert list(event.embedding) == _vector()
    assert event.embedding_model == get_settings().embedding_model
    # The embedding's own tokens and cost are added on top of the
    # caller's; `completion_tokens` stays the caller's value alone.
    assert event.prompt_tokens == 100 + 8
    assert event.completion_tokens == 40
    assert event.cost_usd == 0.5 + 0.25


# --- AC3 -- every non-narration kind stores nothing and calls out never ----


def test_ac3_a_player_action_and_a_system_event_store_no_vector_and_never_call_out():
    # <- AC3
    calls: list = []

    def recording_embed_texts(texts, *, model=None):
        calls.append(list(texts))
        return EmbeddingResult(
            vectors=[_vector()],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=None),
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(llm_service, "embed_texts", recording_embed_texts)
        db = _RecordingSession()

        action_event = asyncio.run(
            playthrough_service.append_event(
                db,
                run_id=generate_id(),
                type="player_action",
                visibility="player",
                payload={"text": "I search the room for traps."},
            )
        )
        system_event = asyncio.run(
            playthrough_service.append_event(
                db,
                run_id=generate_id(),
                type="system",
                visibility="player",
                payload={"message": "Autosaved."},
            )
        )

    assert calls == []
    assert action_event.embedding is None
    assert action_event.embedding_model is None
    assert system_event.embedding is None
    assert system_event.embedding_model is None


# --- AC4 -- an embedding failure never reaches the caller -------------------


def test_ac4_when_embed_texts_raises_the_narration_row_still_writes_with_a_null_vector_and_warns():
    # <- AC4, "any exception, classified or not" -- an ordinary exception
    # and one of the seam's own classified errors, each its own scope.
    for exc_to_raise in (RuntimeError("boom"), LlmConfigurationError()):
        with pytest.MonkeyPatch.context() as mp:

            def failing_embed_texts(texts, *, model=None, _exc=exc_to_raise):
                raise _exc

            mp.setattr(llm_service, "embed_texts", failing_embed_texts)
            db = _RecordingSession()

            with structlog.testing.capture_logs() as logs:
                event = asyncio.run(
                    playthrough_service.append_event(
                        db,
                        run_id="a-run-id",
                        type="narration",
                        visibility="player",
                        payload={"text": "The tavern falls silent as you enter."},
                    )
                )

        # The row is still written -- same object the success path would
        # hand back, with only the embedding columns left empty.
        assert event in db.added
        assert event.type == "narration"
        assert event.payload == {"text": "The tavern falls silent as you enter."}
        assert event.embedding is None
        assert event.embedding_model is None

        warnings = [entry for entry in logs if entry.get("log_level") == "warning"]
        assert len(warnings) == 1, logs
        assert warnings[0]["event"] == "narration_embedding_failed"


# --- AC5 -- the CLI writes narration or a player action and prints the id --


def test_ac5_narrate_appends_through_append_event_and_prints_the_new_events_id_and_no_route_exists(
    client,
):
    # <- AC5
    run_id = generate_id()

    with pytest.MonkeyPatch.context() as mp:
        captured: dict = {}

        async def fake_append_event(db, **kwargs):
            captured.update(kwargs)
            return type("Event", (), {"id": "01NARRATIONEVENTIDXXXXXXXX"})()

        mp.setattr(playthrough_service, "append_event", fake_append_event)

        result = runner.invoke(cli, ["playthrough", "narrate", run_id, "It begins."])

        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        assert result.stdout == "event: 01NARRATIONEVENTIDXXXXXXXX\n"
        assert captured.get("run_id") == run_id
        assert captured.get("type") == "narration"
        assert captured.get("visibility") == "player"
        assert captured.get("payload") == {"text": "It begins."}

    # The `--player-action` flag switches the kind, nothing else.
    with pytest.MonkeyPatch.context() as mp:
        captured_action: dict = {}

        async def fake_append_event_action(db, **kwargs):
            captured_action.update(kwargs)
            return type("Event", (), {"id": "01PLAYERACTIONEVENTIDXXXXX"})()

        mp.setattr(playthrough_service, "append_event", fake_append_event_action)

        result = runner.invoke(
            cli, ["playthrough", "narrate", run_id, "I draw my sword.", "--player-action"]
        )

        assert result.exit_code == 0, result.output
        assert result.stdout == "event: 01PLAYERACTIONEVENTIDXXXXX\n"
        assert captured_action.get("type") == "player_action"
        assert captured_action.get("payload") == {"text": "I draw my sword."}

    # A refusal from the writer prints `{code}: {message}` on stderr, exit 1.
    with pytest.MonkeyPatch.context() as mp:

        async def failing_append_event(db, **kwargs):
            raise CampaignRunNotFoundError(run_id)

        mp.setattr(playthrough_service, "append_event", failing_append_event)

        result = runner.invoke(cli, ["playthrough", "narrate", run_id, "It begins."])

        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr.strip() == f"NOT_FOUND: campaign run not found: {run_id}"

    # No HTTP route exposes narration writing.
    openapi_document = client.get("/openapi.json").json()
    for path, operations in openapi_document["paths"].items():
        assert "narrate" not in path.lower(), path
        for operation in operations.values():
            if isinstance(operation, dict):
                assert "narrate" not in str(operation.get("operationId", "")).lower(), path
