"""WI1: `events.embedding`/`events.embedding_model` round-trip against a
real, migrated database, and the `ix_events_embedding_narration` partial
index covers only narration rows that carry a vector (AC1). Marked
`database`: skipped under `make backend-test` (no reachable Postgres,
`--no-deps`), run for real under `make backend-test-db`. No
`pytest-asyncio` in this suite (`AGENTS.md` gotchas) -- every async call is
wrapped in a single `asyncio.run(...)` per test."""

import asyncio

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.modules.playthrough.models import EMBEDDING_WIDTH


async def _insert_campaign_run(session, run_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version) "
            "VALUES (:id, 'campaign-1', 'v1')"
        ),
        {"id": run_id},
    )


@pytest.mark.database
def test_ac1_both_embedding_columns_are_optional_and_survive_a_write_then_read(playthrough_db):
    # <- AC1: an event written with neither column set reads back NULL for
    # both; one written with both set reads back the same vector and model
    # name it was given.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id)
        await playthrough_db.commit()

        bare_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                "VALUES (:id, :campaign_run_id, 'narration', 'player', '{}'::jsonb)"
            ),
            {"id": bare_id, "campaign_run_id": campaign_run_id},
        )
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT embedding, embedding_model FROM events WHERE id = :id"), {"id": bare_id}
        )
        found = row.first()
        assert found.embedding is None
        assert found.embedding_model is None

        vector = [0.5] * EMBEDDING_WIDTH
        embedded_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO events "
                "(id, campaign_run_id, type, visibility, payload, embedding, embedding_model) "
                "VALUES (:id, :campaign_run_id, 'narration', 'player', '{}'::jsonb, "
                ":embedding, :embedding_model)"
            ),
            {
                "id": embedded_id,
                "campaign_run_id": campaign_run_id,
                "embedding": str(vector),
                "embedding_model": "text-embedding-3-small",
            },
        )
        await playthrough_db.commit()
        row = await playthrough_db.execute(
            text("SELECT embedding::text AS embedding, embedding_model FROM events WHERE id = :id"),
            {"id": embedded_id},
        )
        found = row.first()
        read_back = [float(value) for value in found.embedding.strip("[]").split(",")]
        assert read_back == pytest.approx(vector)
        assert found.embedding_model == "text-embedding-3-small"

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_the_narration_index_covers_only_embedded_narration_rows(playthrough_db):
    # <- AC1: the partial index predicate on `pg_indexes` names both the
    # `narration` type restriction and the not-null embedding restriction,
    # so a `roll` row or a narration row with no vector is never covered.
    async def _scenario():
        row = await playthrough_db.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'events' AND indexname = 'ix_events_embedding_narration'"
            )
        )
        indexdef = row.scalar()
        assert indexdef is not None
        assert "hnsw" in indexdef
        assert "vector_cosine_ops" in indexdef
        assert "narration" in indexdef
        assert "embedding IS NOT NULL" in indexdef

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac1_migration_0008_touches_nothing_0007_owns(playthrough_db):
    # <- AC1: the schema this migration leaves behind still accepts every
    # value `0007` introduced -- proof this step never narrowed what `0007`
    # widened.
    async def _scenario():
        campaign_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, campaign_run_id)
        await playthrough_db.commit()

        row = await playthrough_db.execute(
            text("SELECT status FROM campaign_runs WHERE id = :id"), {"id": campaign_run_id}
        )
        assert row.first().status == "setup"

        for event_type in ("roll_requested", "question", "warning"):
            await playthrough_db.execute(
                text(
                    "INSERT INTO events (id, campaign_run_id, type, visibility, payload) "
                    "VALUES (:id, :campaign_run_id, :type, 'player', '{}'::jsonb)"
                ),
                {"id": generate_id(), "campaign_run_id": campaign_run_id, "type": event_type},
            )
            await playthrough_db.commit()

    asyncio.run(_scenario())
