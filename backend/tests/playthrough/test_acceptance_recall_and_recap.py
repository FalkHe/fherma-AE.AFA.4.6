"""qa acceptance tests -- sprint 006/02 "recall by meaning, and a recap on
return"
(`docs/intents/006-journal-memory/sprints/02-recall-by-meaning-and-recap
/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`,
`.schemas` or `.commands` themselves -- those are this sprint's own work
items, written in parallel, and this file never reads them.

AC1 and AC3 carry `@pytest.mark.database`: ordering by cosine distance is
real pgvector arithmetic, not something a fake session can stand in for and
still prove anything, over the shared `playthrough_db` fixture (`tests
/playthrough/conftest.py`, pinned to `EMBEDDING_DIMENSIONS="1536"` per this
sprint's own plan). Both arrange their rows with plain SQL against the
tables sprint 006/01 and earlier sprints already shipped (`campaign_runs`,
`adventure_runs`, `events`) -- never through `service.append_event` or
`service.start_campaign_run`, so this file never depends on those
functions' own validation to get narration rows with a chosen vector into
place. `embed_texts` is monkeypatched on the module the interface names --
`app.core.llm.service` -- never on whatever alias `playthrough.service`
imports it under (I2).

Every stored vector is the full 1536-wide `EMBEDDING_WIDTH` fixed by the
sprint's own interface contract, never the suite-wide `EMBEDDING_DIMENSIONS`
pin of `4` (`tests/conftest.py`), which belongs to a different module
entirely.

AC2 and AC4 need no database: I2 spells out `recap`'s exact query and its
`list(reversed(rows))` shape precisely so this is provable against a
stubbed `AsyncSession` whose `execute()` never parses the statement it is
handed -- one canned result answers both the module's own existing
run-lookup (however that is shaped) and the narration read, so this file
never has to guess which of `scalar_one_or_none()` / `scalars().first()`
/ `mappings()` that lookup happens to call.

AC5 drives the real `cli` through `CliRunner`, with only
`playthrough_service.recall` / `.recap` monkeypatched -- `tests/srd
/test_commands.py`'s style, also used by this suite's own
`test_acceptance_narration_remembered.py`.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas); every async call
outside the CLI scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
schemas or commands themselves -- this suite is red until the
corresponding work items land, and green once they do.
"""

import asyncio
import json
from collections import namedtuple
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.ids import generate_id
from app.core.llm import service as llm_service
from app.core.llm.service import EmbeddingResult, Usage
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.schemas import NarrationRead

runner = CliRunner()

EMBEDDING_WIDTH = 1536  # fixed by the sprint's own interface contract (I1/I2)


# --- vector helpers, shared by AC1 and AC3 ---------------------------------


def _basis(index: int, width: int = EMBEDDING_WIDTH) -> list[float]:
    vector = [0.0] * width
    vector[index] = 1.0
    return vector


def _opposite(vector: list[float]) -> list[float]:
    return [-value for value in vector]


def _sum(*vectors: list[float]) -> list[float]:
    return [sum(components) for components in zip(*vectors, strict=True)]


QUERY_VECTOR = _basis(0)  # the query always embeds to this
VECTOR_IDENTICAL = _basis(0)  # cosine distance 0 -- closest possible
VECTOR_ANGLED = _sum(_basis(0), _basis(1))  # ~45 degrees away
VECTOR_OPPOSITE = _opposite(_basis(0))  # cosine distance 2 -- farthest possible


def _stub_embed_texts(monkeypatch_ctx, vector: list[float], calls: list) -> None:
    """Monkeypatches the exact seam I2 names -- `app.core.llm.service
    .embed_texts`, a module attribute, never whatever alias `playthrough
    .service` imports it under -- to answer a fixed vector and record every
    call it received."""

    def fake_embed_texts(texts, *, model=None):
        calls.append(list(texts))
        return EmbeddingResult(
            vectors=[vector],
            usage=Usage(prompt_tokens=1, completion_tokens=0, total_tokens=1, cost_usd=None),
        )

    monkeypatch_ctx.setattr(llm_service, "embed_texts", fake_embed_texts)


# --- database arrangement helpers, shared by AC1 and AC3 -------------------


async def _insert_campaign_run(session, run_id: str) -> None:
    await session.execute(
        text(
            "INSERT INTO campaign_runs (id, campaign_id, content_version) "
            "VALUES (:id, 'greenhollow', 'v1')"
        ),
        {"id": run_id},
    )


async def _insert_narration(
    session,
    event_id: str,
    run_id: str,
    *,
    content: str,
    vector: list[float] | None,
    created_at: datetime | None = None,
) -> None:
    """One `narration` row, embedded or not, at a chosen (or default-now)
    timestamp -- direct SQL, never `service.append_event`, so this file
    never depends on that function's own validation to arrange its rows."""
    vector_literal = None if vector is None else "[" + ",".join(str(v) for v in vector) + "]"
    await session.execute(
        text(
            "INSERT INTO events (id, campaign_run_id, type, visibility, payload, embedding, "
            "embedding_model, created_at) VALUES (:id, :run_id, 'narration', 'player', "
            "CAST(:payload AS jsonb), CAST(:embedding AS vector), :model, "
            "COALESCE(:created_at, now()))"
        ),
        {
            "id": event_id,
            "run_id": run_id,
            "payload": json.dumps({"text": content}),
            "embedding": vector_literal,
            "model": None if vector is None else "test/embedding-model",
            "created_at": created_at,
        },
    )


def _assert_narration_read_shape(items) -> None:
    """I1: exactly `id`, `created_at`, `text`, in that order -- no
    distance, no payload, no vector -- for every item either read
    returns."""
    assert list(NarrationRead.model_fields) == ["id", "created_at", "text"]
    for item in items:
        assert isinstance(item, NarrationRead), item
        assert isinstance(item.id, str)
        assert isinstance(item.created_at, datetime)
        assert isinstance(item.text, str)


# --- engine-free stand-in for AC2/AC4 ---------------------------------------


_Row = namedtuple("_Row", ["id", "created_at", "payload"])
"""A DB row answering both attribute (`row.id`) and positional
(`event_id, created_at, payload = row`) access -- the two shapes a real
`Row` from `select(Event.id, Event.created_at, Event.payload)` (I2)
supports -- so this file never has to guess which style the module's own
read code prefers."""


class _StubResult:
    """Stands in for whatever `AsyncSession.execute()` returns -- answers
    every plausible accessor with either the canned rows or a truthy
    stand-in, so this file never has to know the exact shape of "the
    module's existing run lookup" (I2) or how the narration read pulls its
    rows out."""

    def __init__(self, rows: list[_Row]):
        self._rows = rows

    def scalar_one_or_none(self):
        return True

    def scalar(self):
        return True

    def one_or_none(self):
        return True

    def first(self):
        return True

    def scalars(self):
        return self

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _StubSession:
    """Engine-free stand-in for `AsyncSession`. `execute()` never parses
    the statement it is handed -- the same `_StubResult` answers however
    many calls `recap` makes, in whatever order, per I2's own design note
    that this is what makes AC4 provable without a database."""

    def __init__(self, rows: list[_Row]):
        self._result = _StubResult(rows)

    async def execute(self, _stmt):
        return self._result

    async def get(self, _model, _ident):
        return True


# --- AC1 -- recall orders by meaning, excludes what never embedded ---------


@pytest.mark.database
def test_ac1_recall_orders_by_cosine_distance_and_excludes_unembedded_rows(playthrough_db):
    # <- AC1
    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        await playthrough_db.commit()

        closest_id = generate_id()
        mid_id = generate_id()
        farthest_id = generate_id()
        unembedded_id = generate_id()

        await _insert_narration(
            playthrough_db, closest_id, run_id, content="the closest line", vector=VECTOR_IDENTICAL
        )
        await _insert_narration(
            playthrough_db, mid_id, run_id, content="the middling line", vector=VECTOR_ANGLED
        )
        await _insert_narration(
            playthrough_db,
            farthest_id,
            run_id,
            content="the farthest line, still returned",
            vector=VECTOR_OPPOSITE,
        )
        await _insert_narration(
            playthrough_db, unembedded_id, run_id, content="never returned", vector=None
        )
        await playthrough_db.commit()

        calls: list = []
        with pytest.MonkeyPatch.context() as mp:
            _stub_embed_texts(mp, QUERY_VECTOR, calls)
            result = await playthrough_service.recall(
                playthrough_db, run_id=run_id, query="what happened here", k=3
            )

        # Exactly the three embedded rows, closest first -- the farthest
        # (cosine distance 2, the maximum possible) is still returned: no
        # relevance floor.
        assert [item.id for item in result] == [closest_id, mid_id, farthest_id]
        assert unembedded_id not in [item.id for item in result]
        by_id = {item.id: item for item in result}
        assert by_id[closest_id].text == "the closest line"
        assert by_id[farthest_id].text == "the farthest line, still returned"
        _assert_narration_read_shape(result)

        # The query is embedded exactly once.
        assert calls == [["what happened here"]]

        # A run with no narration at all returns nothing.
        empty_run_id = generate_id()
        await _insert_campaign_run(playthrough_db, empty_run_id)
        await playthrough_db.commit()
        with pytest.MonkeyPatch.context() as mp:
            _stub_embed_texts(mp, QUERY_VECTOR, [])
            empty_result = await playthrough_service.recall(
                playthrough_db, run_id=empty_run_id, query="anything", k=5
            )
        assert empty_result == []

    asyncio.run(_scenario())


# --- AC3 -- the search spans the whole run, not one adventure --------------


@pytest.mark.database
def test_ac3_recall_returns_an_earlier_adventures_line_when_it_is_the_closest(playthrough_db):
    # <- AC3
    async def _scenario():
        run_id = generate_id()
        await _insert_campaign_run(playthrough_db, run_id)
        await playthrough_db.commit()

        first_adventure_id = generate_id()
        second_adventure_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO adventure_runs (id, campaign_run_id, adventure_id, status, "
                "completed_at) VALUES (:id, :run_id, 'greenhollow-intro', 'completed', "
                "'2020-06-01T00:00:00Z')"
            ),
            {"id": first_adventure_id, "run_id": run_id},
        )
        await playthrough_db.execute(
            text(
                "INSERT INTO adventure_runs (id, campaign_run_id, adventure_id, status, "
                "started_at) VALUES (:id, :run_id, 'greenhollow-crypt', 'active', "
                "'2023-01-01T00:00:00Z')"
            ),
            {"id": second_adventure_id, "run_id": run_id},
        )
        await playthrough_db.commit()

        # One line written during the first (now completed) adventure,
        # semantically the closest match; one line written later, during
        # the second (currently active) adventure, semantically far off.
        early_id = generate_id()
        late_id = generate_id()
        await _insert_narration(
            playthrough_db,
            early_id,
            run_id,
            content="a line from the first adventure",
            vector=VECTOR_IDENTICAL,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        await _insert_narration(
            playthrough_db,
            late_id,
            run_id,
            content="a line from the second adventure",
            vector=VECTOR_OPPOSITE,
            created_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        await playthrough_db.commit()

        calls: list = []
        with pytest.MonkeyPatch.context() as mp:
            _stub_embed_texts(mp, QUERY_VECTOR, calls)
            result = await playthrough_service.recall(
                playthrough_db, run_id=run_id, query="the first adventure", k=1
            )

        # The older, first-adventure line wins on meaning alone -- not
        # recency, and not adventure boundary.
        assert len(result) == 1
        assert result[0].id == early_id
        assert result[0].text == "a line from the first adventure"

    asyncio.run(_scenario())


# --- AC2 -- recap answers with recency alone, oldest of the chosen first --


def test_ac2_recap_returns_the_n_most_recent_events_in_chronological_order():
    # <- AC2
    run_id = generate_id()

    # SQL already hands back the newest `n`, newest first (I2's own
    # `.order_by(Event.id.desc()).limit(n)`); `recap` reverses them.
    newer = _Row(
        id="01NEWERNEWERNEWERNEWERNEW",
        created_at=datetime(2026, 1, 2, tzinfo=UTC),
        payload={"text": "the more recent line"},
    )
    older = _Row(
        id="01OLDEROLDEROLDEROLDEROLD",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"text": "the older line"},
    )
    db = _StubSession(rows=[newer, older])

    result = asyncio.run(playthrough_service.recap(db, run_id=run_id, n=2))

    assert [item.id for item in result] == [older.id, newer.id]  # oldest first
    assert [item.text for item in result] == ["the older line", "the more recent line"]
    _assert_narration_read_shape(result)

    # A run with no narration returns nothing.
    empty_db = _StubSession(rows=[])
    empty_result = asyncio.run(playthrough_service.recap(empty_db, run_id=run_id, n=5))
    assert empty_result == []


# --- AC4 -- recap never asks anything of the encoder ------------------------


def test_ac4_recap_makes_no_embedding_call():
    # <- AC4
    run_id = generate_id()
    row = _Row(
        id="01AROWAROWAROWAROWAROWARO",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        payload={"text": "a line"},
    )
    db = _StubSession(rows=[row])

    calls: list = []
    with pytest.MonkeyPatch.context() as mp:

        def failing_embed_texts(texts, *, model=None):
            calls.append(list(texts))
            raise AssertionError("recap must never embed anything")

        mp.setattr(llm_service, "embed_texts", failing_embed_texts)

        result = asyncio.run(playthrough_service.recap(db, run_id=run_id, n=5))

    assert calls == []
    assert [item.id for item in result] == [row.id]


# --- AC5 -- both reads are usable from the command line ---------------------


def test_ac5_recall_and_recap_commands_print_one_line_per_event_and_refuse_an_unknown_run():
    # <- AC5
    run_id = generate_id()

    # -- recall: one line per event, `id created_at.isoformat() text`,
    # `k` defaults to 5 and reaches the service.
    with pytest.MonkeyPatch.context() as mp:
        captured: dict = {}

        async def fake_recall(db, **kwargs):
            captured.update(kwargs)
            return [
                SimpleNamespace(
                    id="01AAAAAAAAAAAAAAAAAAAAAAAA",
                    created_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
                    text="A goblin steps out of the shadows.",
                ),
                SimpleNamespace(
                    id="01BBBBBBBBBBBBBBBBBBBBBBBB",
                    created_at=datetime(2026, 1, 2, 8, 30, 0, tzinfo=UTC),
                    text="The tavern falls silent.",
                ),
            ]

        mp.setattr(playthrough_service, "recall", fake_recall)

        result = runner.invoke(cli, ["playthrough", "recall", run_id, "goblins"])

        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        assert result.stdout == (
            "01AAAAAAAAAAAAAAAAAAAAAAAA 2026-01-01T12:00:00+00:00 "
            "A goblin steps out of the shadows.\n"
            "01BBBBBBBBBBBBBBBBBBBBBBBB 2026-01-02T08:30:00+00:00 The tavern falls silent.\n"
        )
        assert captured.get("run_id") == run_id
        assert captured.get("query") == "goblins"
        assert captured.get("k") == 5

    # -- `--k` overrides the default; an empty result prints nothing and
    # exits 0.
    with pytest.MonkeyPatch.context() as mp:
        captured_k: dict = {}

        async def fake_recall_k(db, **kwargs):
            captured_k.update(kwargs)
            return []

        mp.setattr(playthrough_service, "recall", fake_recall_k)

        result = runner.invoke(cli, ["playthrough", "recall", run_id, "goblins", "--k", "2"])

        assert result.exit_code == 0, result.output
        assert result.stdout == ""
        assert captured_k.get("k") == 2

    # -- an unknown run refuses with `{code}: {message}` on stderr, exit 1.
    with pytest.MonkeyPatch.context() as mp:

        async def failing_recall(db, **kwargs):
            raise CampaignRunNotFoundError(run_id)

        mp.setattr(playthrough_service, "recall", failing_recall)

        result = runner.invoke(cli, ["playthrough", "recall", run_id, "goblins"])

        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr.strip() == f"NOT_FOUND: campaign run not found: {run_id}"

    # -- recap: same per-line shape, `n` defaults to 5 and reaches the
    # service.
    with pytest.MonkeyPatch.context() as mp:
        captured_recap: dict = {}

        async def fake_recap(db, **kwargs):
            captured_recap.update(kwargs)
            return [
                SimpleNamespace(
                    id="01CCCCCCCCCCCCCCCCCCCCCCCC",
                    created_at=datetime(2026, 2, 1, 9, 0, 0, tzinfo=UTC),
                    text="You return to the tavern.",
                ),
            ]

        mp.setattr(playthrough_service, "recap", fake_recap)

        result = runner.invoke(cli, ["playthrough", "recap", run_id])

        assert result.exit_code == 0, result.output
        assert result.stdout == (
            "01CCCCCCCCCCCCCCCCCCCCCCCC 2026-02-01T09:00:00+00:00 You return to the tavern.\n"
        )
        assert captured_recap.get("run_id") == run_id
        assert captured_recap.get("n") == 5

    # -- `--n` overrides the default; an empty result prints nothing and
    # exits 0.
    with pytest.MonkeyPatch.context() as mp:
        captured_recap_n: dict = {}

        async def fake_recap_n(db, **kwargs):
            captured_recap_n.update(kwargs)
            return []

        mp.setattr(playthrough_service, "recap", fake_recap_n)

        result = runner.invoke(cli, ["playthrough", "recap", run_id, "--n", "3"])

        assert result.exit_code == 0, result.output
        assert result.stdout == ""
        assert captured_recap_n.get("n") == 3

    # -- an unknown run refuses the same way.
    with pytest.MonkeyPatch.context() as mp:

        async def failing_recap(db, **kwargs):
            raise CampaignRunNotFoundError(run_id)

        mp.setattr(playthrough_service, "recap", failing_recap)

        result = runner.invoke(cli, ["playthrough", "recap", run_id])

        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr.strip() == f"NOT_FOUND: campaign run not found: {run_id}"
