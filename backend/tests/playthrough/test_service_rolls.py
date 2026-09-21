"""WI2 (sprint 07a): asking a player to roll, answering that request,
rolling outright, a passive check, and asking a question -- AC2, the
`ask_player` half of AC4a.

qa's own `test_acceptance_rolls_derived_and_recorded.py` already drives
the full happy path for every producer plus the "no producer takes a
number" structural check; this file covers what that black-box suite
does not: the gate order these functions share with `use_exit` (an
unknown/foreign actor or run, an archived run, an invalid status), the
`resolve_roll_request` re-use rule (the stored formula decides, never a
re-derivation), an unknown request id, and a passive check's failing
branch.

Gates are engine-free (`FakeSession`, the same shape
`test_service_use_exit.py` uses); everything that needs a real roll or a
real read-back is `@pytest.mark.database`, with `dice._rng` monkeypatched
so faces are fixed and assertable (AGENTS.md: "replace the random
source").

No `pytest-asyncio` in this suite (AGENTS.md gotchas): every async call is
wrapped in a single `asyncio.run(...)` per test.
"""

import asyncio
from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.playthrough import dice, service
from app.modules.playthrough.errors import (
    CampaignRunNotFoundError,
    GameObjectNotFoundError,
    InvalidRunStatusError,
    RollRequestNotFoundError,
    RunArchivedError,
)
from app.modules.playthrough.models import CampaignRun, CampaignRunMember, GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


async def _insert_user(session: AsyncSession, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _ScriptedRandom:
    """A fixed, in-order sequence of face values -- `dice._rng`'s
    replacement, not the stdlib module (AGENTS.md's dice gotcha)."""

    def __init__(self, values: Iterator[int]):
        self._values = values

    def randint(self, a: int, b: int) -> int:
        return next(self._values)


async def _new_character(db, *, user_id: str):
    run = await service.start_campaign_run(db, user_id=user_id, campaign_id=CAMPAIGN_ID)
    character = await service.create_character(db, user_id=user_id, run_id=run.id)
    return run, character


async def _event_row(db, event_id: str):
    return (
        await db.execute(
            text("SELECT type, visibility, payload FROM events WHERE id = :id"), {"id": event_id}
        )
    ).one()


# --- gates, engine-free (FakeSession, `test_service_use_exit.py`'s shape) -


class FakeResult:
    def __init__(self, *, scalar=None):
        self._scalar = scalar

    def scalar_one_or_none(self):
        return self._scalar


class FakeSession:
    def __init__(self, *results):
        self._results = list(results)
        self.added: list[object] = []
        self.committed = 0

    async def execute(self, stmt):
        return self._results.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed += 1


def _object(object_id="actor-1", *, campaign_run_id="run-1"):
    return GameObject(
        id=object_id,
        campaign_run_id=campaign_run_id,
        kind="creature",
        template_id=None,
        instance_key="pc:member-1:1",
        name="Fixture Actor",
        state={"abilities": {}},
    )


def _member(run_id="run-1", user_id="user-1"):
    return CampaignRunMember(campaign_run_id=run_id, user_id=user_id, role="owner")


def _run(run_id="run-1", *, status="ready"):
    return CampaignRun(id=run_id, campaign_id=CAMPAIGN_ID, content_version=VERSION, status=status)


def test_request_player_roll_raises_game_object_not_found_for_an_unknown_actor():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(GameObjectNotFoundError):
        asyncio.run(
            service.request_player_roll(
                db, user_id="user-1", actor_id="no-such-actor", kind="initiative", context={}
            )
        )
    assert db.added == []
    assert db.committed == 0


def test_roll_raises_campaign_run_not_found_for_an_actor_on_a_foreign_run():
    db = FakeSession(FakeResult(scalar=_object()), FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(
            service.roll(db, user_id="user-1", actor_id="actor-1", kind="initiative", context={})
        )
    assert db.added == []
    assert db.committed == 0


def test_passive_check_raises_run_archived_for_an_archived_run():
    db = FakeSession(
        FakeResult(scalar=_object()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status="archived")),
    )

    with pytest.raises(RunArchivedError):
        asyncio.run(
            service.passive_check(
                db, user_id="user-1", actor_id="actor-1", ability="wisdom", dc=10
            )
        )
    assert db.committed == 0


@pytest.mark.parametrize("status", ["setup", "finished"])
def test_request_player_roll_raises_invalid_run_status_outside_ready_or_active(status):
    db = FakeSession(
        FakeResult(scalar=_object()),
        FakeResult(scalar=_member()),
        FakeResult(scalar=_run(status=status)),
    )

    with pytest.raises(InvalidRunStatusError):
        asyncio.run(
            service.request_player_roll(
                db, user_id="user-1", actor_id="actor-1", kind="initiative", context={}
            )
        )
    assert db.committed == 0


def test_ask_player_raises_campaign_run_not_found_for_a_foreign_run():
    db = FakeSession(FakeResult(scalar=None))

    with pytest.raises(CampaignRunNotFoundError):
        asyncio.run(
            service.ask_player(db, user_id="user-1", run_id="run-1", text="Well?", options=[])
        )
    assert db.added == []
    assert db.committed == 0


# --- the real thing: a real request, a real answer, a real database -------


@pytest.mark.database
def test_resolve_roll_request_reuses_the_requests_own_stored_values(playthrough_db):
    # <- AC2: the answer carries the request's own formula, kind, actor id
    # and visibility, never a fresh derivation.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-reuse")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        requested = await service.request_player_roll(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "dexterity"},
        )
        request_row = await _event_row(playthrough_db, requested.id)
        assert request_row.visibility == "player"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(dice, "_rng", lambda: _ScriptedRandom(iter([9])))
            answered = await service.resolve_roll_request(
                playthrough_db, user_id=user_id, request_id=requested.id
            )

        answer_row = await _event_row(playthrough_db, answered.id)
        assert answer_row.type == "roll"
        assert answer_row.visibility == request_row.visibility == "player"
        assert answer_row.payload["formula"] == request_row.payload["formula"]
        assert answer_row.payload["kind"] == "ability_check"
        assert answer_row.payload["actorId"] == character.id
        assert answer_row.payload["faces"] == [9]
        dexterity_modifier = (
            content_service.load_campaign(CAMPAIGN_ID, VERSION).campaign.seed_character.abilities.dexterity
            - 10
        ) // 2
        assert answer_row.payload["modifier"] == dexterity_modifier
        assert answer_row.payload["total"] == 9 + dexterity_modifier

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_roll_request_raises_for_an_unknown_request_id(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-unknown")
        await playthrough_db.commit()

        with pytest.raises(RollRequestNotFoundError):
            await service.resolve_roll_request(
                playthrough_db, user_id=user_id, request_id=generate_id()
            )

    asyncio.run(_scenario())


@pytest.mark.database
def test_resolve_roll_request_raises_for_an_event_that_is_not_a_request(playthrough_db):
    # <- a `question` (or any other type) is not answerable as a roll.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="resolve-wrong-type")
        await playthrough_db.commit()
        run, _ = await _new_character(playthrough_db, user_id=user_id)

        question = await service.ask_player(
            playthrough_db, user_id=user_id, run_id=run.id, text="Well?", options=[]
        )

        with pytest.raises(RollRequestNotFoundError):
            await service.resolve_roll_request(
                playthrough_db, user_id=user_id, request_id=question.id
            )

    asyncio.run(_scenario())


@pytest.mark.database
def test_roll_derives_and_rolls_in_one_call_with_no_prior_request(playthrough_db):
    # <- AC2: rolling outright still leaves a `roll_requested` behind it,
    # both at the caller's chosen visibility.
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="roll-outright")
        await playthrough_db.commit()
        _, character = await _new_character(playthrough_db, user_id=user_id)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(dice, "_rng", lambda: _ScriptedRandom(iter([1])))
            rolled = await service.roll(
                playthrough_db,
                user_id=user_id,
                actor_id=character.id,
                kind="initiative",
                context={},
                visibility="player",
            )

        roll_row = await _event_row(playthrough_db, rolled.id)
        assert roll_row.visibility == "player"
        assert roll_row.payload["faces"] == [1]

        request_row = await _event_row(playthrough_db, roll_row.payload["requestId"])
        assert request_row.type == "roll_requested"
        assert request_row.visibility == "player"
        assert request_row.payload["kind"] == "initiative"

    asyncio.run(_scenario())


@pytest.mark.database
def test_passive_check_fails_when_the_passive_score_is_below_the_dc(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="passive-fail")
        await playthrough_db.commit()
        run, character = await _new_character(playthrough_db, user_id=user_id)

        wisdom = content_service.load_campaign(
            CAMPAIGN_ID, VERSION
        ).campaign.seed_character.abilities.wisdom
        passive_score = 10 + (wisdom - 10) // 2

        passed = await service.passive_check(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            ability="wisdom",
            dc=passive_score + 1,
        )
        assert passed is False

        row = (
            await playthrough_db.execute(
                text(
                    "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).one()
        assert row.payload["outcome"]["success"] is False
        assert "faces" not in row.payload

    asyncio.run(_scenario())


@pytest.mark.database
def test_ask_player_appends_a_question_at_player_visibility(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="ask-player")
        await playthrough_db.commit()
        run, _ = await _new_character(playthrough_db, user_id=user_id)

        event = await service.ask_player(
            playthrough_db,
            user_id=user_id,
            run_id=run.id,
            text="Which way?",
            options=["north", "south"],
        )

        row = await _event_row(playthrough_db, event.id)
        assert row.type == "question"
        assert row.visibility == "player"
        assert row.payload == {"text": "Which way?", "options": ["north", "south"]}

    asyncio.run(_scenario())
