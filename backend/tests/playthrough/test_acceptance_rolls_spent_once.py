"""qa acceptance tests -- sprint 005/07b "a roll is spent once, and the
client sees what is awaited"
(`docs/intents/005-game-state-services/sprints/07b-rolls-spent-once/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`'s
new functions (`resolve_check`, `resolve_save`, `_consume_roll`,
`get_awaiting`), `.errors` or `.routes` themselves -- those are this
sprint's own work items, written in parallel, and this file never reads
them. `app.modules.playthrough.dice` and the roll *producers*
(`roll`, `request_player_roll`, `resolve_roll_request`, `ask_player`) are
sprint 07a's, already merged to `main`, and are used here exactly as the
07a acceptance suite (`test_acceptance_rolls_derived_and_recorded.py`) uses
them -- to build the rolls this sprint's consumers spend.

AC3 needs the real database (`@pytest.mark.database`): it produces several
rolls through the real producers -- `dice._rng` is monkeypatched, scoped to
`pytest.MonkeyPatch.context()` per call, to a small scripted
`random.Random` subclass (same seam and subclass 07a's own suite uses) so
each roll's `total` is a known number and pass/fail can be asserted for
real rather than merely "some boolean came back" -- then drives
`resolve_check` / `resolve_save` directly and reads the outcome back with
plain SQL over `events`, never the ORM model classes for anything this
sprint writes (same pattern as `test_acceptance_transcript_writer_and_
read.py` / `test_acceptance_exits_and_endings.py`).

Every refusal's persisted record is read back from a **second** connection
to the same scratch database, opened only after every refusing call has
already raised -- never from the session the refusing calls themselves ran
on. A flushed-but-uncommitted row is visible to the session that wrote it
regardless of whether the service ever committed, so that session can
never tell a genuinely persisted refusal apart from one that would vanish
under a caller's rollback; only an independent connection can (same
pattern as `test_acceptance_exits_and_endings.py`'s own `_second_
connection`, in reverse of `test_acceptance_cost_and_live_signal.py`'s
`writer_engine`).

AC4b's wire half (does `GET .../campaign/{run_id}/events` answer
`{events, awaiting}` rather than a bare list) is exercised through
`client` with `list_events` and `get_awaiting` monkeypatched, scoped to its
own `MonkeyPatch.context()` so nothing leaks into the real-database half
that follows -- same split `test_acceptance_transcript_writer_and_read.py`
uses for its own AC2. The real-database half drives `get_awaiting`
directly, never through `TestClient`, so the two halves never touch the
same session (a documented hazard in this suite).

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in one scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
routes or errors modules themselves -- this suite is red until the
corresponding work items land, and green once they do.
"""

import asyncio
import json
import os
import random as random_module
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.content import service as content_service
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service as playthrough_service
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    and subclass `test_acceptance_rolls_derived_and_recorded.py` (07a)
    uses, so a roll's `total` is a known number rather than a real one,
    and pass/fail can be asserted against a concrete difficulty."""

    def __init__(self, faces: list[int]) -> None:
        super().__init__()
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


def _payload(row) -> dict:
    payload = row.payload
    if isinstance(payload, str):
        payload = json.loads(payload)
    return payload


async def _dm_tool_calls(session, run_id: str, *, result: str) -> list[dict]:
    rows = (
        await session.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [p for p in (_payload(row) for row in rows) if p.get("result") == result]


class _second_connection:
    """An `AsyncSession` on its own connection to the same scratch
    database `playthrough_db` already pinned `DATABASE_URL` to -- never a
    session a refusing call itself ran on. The only way to read what is
    genuinely committed rather than merely flushed and still pending in
    the other session's open transaction (same helper as
    `test_acceptance_exits_and_endings.py`)."""

    async def __aenter__(self):
        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


async def _rolled(db, *, user_id, actor_id, kind, context, face, turn_id=None):
    """Produces one real `roll` event through the 07a producer `roll`,
    with `dice._rng` scripted for the duration of this call alone so the
    resulting `total` is a known number."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([face]))
        return await playthrough_service.roll(
            db,
            user_id=user_id,
            actor_id=actor_id,
            kind=kind,
            context=context,
            turn_id=turn_id,
        )


@pytest.mark.database
def test_ac3_a_roll_becomes_pass_or_fail_and_is_spent_exactly_once(playthrough_db):
    # <- AC3
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac3-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        sheet = content_service.load_campaign(CAMPAIGN_ID, VERSION).campaign.seed_character
        wisdom_mod = (sheet.abilities.wisdom - 10) // 2
        dex_mod = (sheet.abilities.dexterity - 10) // 2

        # -- A check, resolved as a pass: the difficulty is set to exactly
        # the roll's own known total, so `total >= dc` is true.
        r1 = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "wisdom"},
            face=15,
        )
        total1 = 15 + wisdom_mod
        dc1 = total1
        assert 5 <= dc1 <= 30, "seed character's wisdom pushed the total outside 5-30"

        check1 = await playthrough_service.resolve_check(
            playthrough_db, user_id=owner_id, roll_id=r1.id, dc=dc1
        )
        assert check1 is True

        ok_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1
        assert ok_calls[0]["rollIds"] == [str(r1.id)]
        assert ok_calls[0]["args"].get("rollId") == str(r1.id)
        assert ok_calls[0]["args"].get("dc") == dc1
        assert ok_calls[0]["outcome"]["total"] == total1
        assert ok_calls[0]["outcome"]["dc"] == dc1
        assert ok_calls[0]["outcome"]["success"] is True

        # -- Pass/fail never lands on the roll itself.
        r1_row = (
            await playthrough_db.execute(
                text("SELECT payload FROM events WHERE id = :id"), {"id": r1.id}
            )
        ).one()
        assert "success" not in _payload(r1_row)
        assert "dc" not in _payload(r1_row)

        # -- A save, resolved as a fail: the difficulty is set comfortably
        # above the roll's own known total.
        r2 = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="saving_throw",
            context={"ability": "dexterity"},
            face=3,
        )
        total2 = 3 + dex_mod
        dc2 = min(30, total2 + 5)
        assert 5 <= dc2 <= 30
        assert total2 < dc2

        save2 = await playthrough_service.resolve_save(
            playthrough_db, user_id=owner_id, roll_id=r2.id, dc=dc2
        )
        assert save2 is False

        ok_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 2
        fail_call = next(c for c in ok_calls if c["rollIds"] == [str(r2.id)])
        assert fail_call["outcome"]["total"] == total2
        assert fail_call["outcome"]["dc"] == dc2
        assert fail_call["outcome"]["success"] is False

        expected_refused_roll_ids: list[str] = []

        # -- The same roll, spent a second time, is refused.
        with pytest.raises(Exception) as double_spend:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r1.id, dc=dc1
            )
        assert double_spend.value.code == ErrorCode.ROLL_NOT_USABLE
        expected_refused_roll_ids.append(str(r1.id))

        # -- A roll from another turn than the one it is spent in is
        # refused, even though the consuming call and the roll are
        # otherwise valid.
        other_turn_id = generate_id()
        r3 = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "wisdom"},
            face=12,
            turn_id=other_turn_id,
        )
        with pytest.raises(Exception) as wrong_turn:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r3.id, dc=10, turn_id=None
            )
        assert wrong_turn.value.code == ErrorCode.ROLL_NOT_USABLE
        expected_refused_roll_ids.append(str(r3.id))

        # -- A roll of the wrong kind for the mechanic (an `initiative`
        # roll offered to a check) is refused.
        r4 = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="initiative",
            context={},
            face=8,
        )
        with pytest.raises(Exception) as wrong_kind:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r4.id, dc=10
            )
        assert wrong_kind.value.code == ErrorCode.ROLL_NOT_USABLE
        expected_refused_roll_ids.append(str(r4.id))

        # -- A difficulty outside 5-30, both below and above, is refused --
        # and neither attempt burns the roll: a later, valid call against
        # the very same roll still succeeds.
        r5 = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=10,
        )
        with pytest.raises(Exception) as dc_low:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r5.id, dc=4
            )
        assert dc_low.value.code == ErrorCode.INVALID_DC
        expected_refused_roll_ids.append(str(r5.id))

        with pytest.raises(Exception) as dc_high:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r5.id, dc=31
            )
        assert dc_high.value.code == ErrorCode.INVALID_DC
        expected_refused_roll_ids.append(str(r5.id))

        strength_mod = (sheet.abilities.strength - 10) // 2
        total5 = 10 + strength_mod
        dc5 = 5
        check5 = await playthrough_service.resolve_check(
            playthrough_db, user_id=owner_id, roll_id=r5.id, dc=dc5
        )
        assert check5 == (total5 >= dc5)

        ok_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 3
        r5_ok = next(c for c in ok_calls if c["rollIds"] == [str(r5.id)])
        assert r5_ok["outcome"]["total"] == total5
        assert r5_ok["outcome"]["dc"] == dc5

        # -- A `custom` roll -- made from an expression, not derived -- is
        # refused by every consumer, never actually resolved by either.
        r6 = await playthrough_service.roll(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="custom",
            context={"expression": "1d6+1"},
        )
        with pytest.raises(Exception) as custom_check:
            await playthrough_service.resolve_check(
                playthrough_db, user_id=owner_id, roll_id=r6.id, dc=10
            )
        assert custom_check.value.code == ErrorCode.ROLL_NOT_USABLE
        expected_refused_roll_ids.append(str(r6.id))

        with pytest.raises(Exception) as custom_save:
            await playthrough_service.resolve_save(
                playthrough_db, user_id=owner_id, roll_id=r6.id, dc=10
            )
        assert custom_save.value.code == ErrorCode.ROLL_NOT_USABLE
        expected_refused_roll_ids.append(str(r6.id))

        # -- None of this is visible to the player: no `tool_call` ever
        # reaches the player-facing transcript.
        player_events = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert not [e for e in player_events if e.type == "tool_call"]

        # -- Every refusal above genuinely persisted -- committed before
        # its `ApiError` was raised -- reachable from a connection that
        # never saw the attempts that wrote them, not merely flushed into
        # the writer's own still-open transaction.
        async with _second_connection() as reader:
            refused_calls = await _dm_tool_calls(reader, run.id, result="refused")
            actual_refused_roll_ids = sorted(
                c["rollIds"][0] for c in refused_calls if c.get("rollIds")
            )
            assert actual_refused_roll_ids == sorted(expected_refused_roll_ids)
            for call in refused_calls:
                assert call["outcome"], call

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4b_the_read_says_what_the_game_awaits(client, session_cookie_header, playthrough_db):
    # <- AC4b
    # -- Wire contract: `GET .../campaign/{run_id}/events` answers an
    # object carrying both the events and what is awaited, not a bare
    # array. Scoped to its own `MonkeyPatch.context()`, not the
    # `monkeypatch` fixture, so this is undone before the real-database
    # half below runs the very same service functions for real -- same
    # split `test_acceptance_transcript_writer_and_read.py` uses for its
    # own AC2, and the same `client` fixture (a stubbed `db` session,
    # never touching `playthrough_db`).
    wire_run_id = generate_id()
    wire_user_id = generate_id()
    csrf_token = "the-matching-csrf-token"  # noqa: S105 - fixture value, not a secret

    with pytest.MonkeyPatch.context() as mp:
        session = make_session(user_id=wire_user_id, csrf_token=csrf_token)
        user = make_user(user_id=wire_user_id)

        async def fake_resolve_session(db, *, token):
            return session

        async def fake_get_user_by_id(db, *, user_id):
            return user

        mp.setattr(auth_service, "resolve_session", fake_resolve_session)
        mp.setattr(users_service, "get_user_by_id", fake_get_user_by_id)

        fake_events = [
            SimpleNamespace(
                id="01AAAAAAAAAAAAAAAAAAAAAAAA",
                type="narration",
                visibility="player",
                turn_id=None,
                payload={"text": "It begins."},
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                campaign_run_id=wire_run_id,
                actor_member_id=None,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=Decimal("0.000100"),
            )
        ]

        async def fake_list_events(db, **kwargs):
            return fake_events

        expected_awaiting = f"roll:{generate_id()}"

        async def fake_get_awaiting(db, *, user_id, run_id):
            return expected_awaiting

        mp.setattr(playthrough_service, "list_events", fake_list_events)
        mp.setattr(playthrough_service, "get_awaiting", fake_get_awaiting)

        response = client.get(
            f"/api/v1/playthrough/campaign/{wire_run_id}/events",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body, dict), body
        assert set(body.keys()) == {"events", "awaiting"}, body
        assert len(body["events"]) == len(fake_events)
        assert body["events"][0]["id"] == fake_events[0].id
        assert body["awaiting"] == expected_awaiting

    # -- Real database, no monkeypatch in effect: `get_awaiting` derived
    # from the open turn's own entries, never from anything stored --
    # nothing, then a roll, then nothing again once it is answered, then a
    # question.
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac4b-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        # Nothing has been asked of the player yet.
        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == "none"

        # A roll has been requested but not yet answered.
        requested = await playthrough_service.request_player_roll(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "wisdom"},
        )
        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == f"roll:{requested.id}"

        # Once answered, nothing is awaited again.
        await playthrough_service.resolve_roll_request(
            playthrough_db, user_id=owner_id, request_id=requested.id
        )
        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == "none"

        # A question put to the player is awaited by its own id.
        await playthrough_service.ask_player(
            playthrough_db,
            user_id=owner_id,
            run_id=run.id,
            text="Which door do you take?",
            options=["left", "right"],
        )
        question_id = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'question' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).scalar_one()
        awaiting = await playthrough_service.get_awaiting(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert awaiting == f"answer:{question_id}"

    asyncio.run(_scenario())
