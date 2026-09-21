"""qa acceptance tests -- sprint 005/08a "a fixture is interacted with, and
a creature acts once a turn"
(`docs/intents/005-game-state-services/sprints/08a-interact-and-one-action/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`'s
new `interact` or `.errors`' new codes -- those are this sprint's own work
items, written in parallel, and this file never reads them. Everything else
driven here (`start_campaign_run`, `create_character`, `enter_adventure`,
`use_exit`, `roll`, `list_events`) is earlier sprints', already merged, used
exactly as their own acceptance suites use them (`test_acceptance_exits_
and_endings.py`, `test_acceptance_rolls_derived_and_recorded.py`,
`test_acceptance_rolls_spent_once.py`).

Both criteria are exercised against the shipped `greenhollow/v1` content
(`backend/content/campaigns/greenhollow/v1/`), read through
`app.modules.content.service.load_campaign` rather than pasted as literals,
so this file survives an authored-content change: the `thorn-screen`
fixture the seed character finds in `lair-maw` (reached from the entry
scene `village-green` through `to-thornway` then `to-lair-maw`, the same
path `test_acceptance_exits_and_endings.py` walks) offers two checks --
one with no `bypassed_by` at all, one bypassed by `shepherds-knife` (and
`notched-cleaver`), and the seed character's own inventory carries a
`shepherds-knife` (`campaign.json`'s `seed_character.inventory`).

`dice._rng` is monkeypatched, scoped to `pytest.MonkeyPatch.context()` per
call, to a small scripted `random.Random` subclass (the same seam and
subclass the 07a/07b acceptance suites use) so a roll's `total` is a known
number and "meets the difficulty" can be asserted for real rather than
merely "some boolean came back".

Every refusal's persisted `tool_call` record is read back from a **second**
connection to the same scratch database, opened only after the refusing
call has already raised -- never from the session that ran it. A
flushed-but-uncommitted row is visible to the session that wrote it
regardless of whether the service ever committed, so that session can
never tell a genuinely persisted refusal apart from one that would vanish
under a caller's rollback; only an independent connection can (same
pattern as `test_acceptance_exits_and_endings.py`'s own `_second_
connection` / `test_acceptance_rolls_spent_once.py`'s copy of it -- this
file copies it a third time rather than promoting it, per the "a helper is
promoted to `core/` (or shared) only once a **second** module calls it,
unchanged" rule not applying across test files that are each owned by a
different sprint).

"No object in the world changes" (AC1) is checked by snapshotting every
`objects` row for the run -- not just the fixture's own -- before and
after each `interact` call, success or refusal alike: interacting reads
the world and writes only the transcript.

With no turn allocator yet (`AGENTS.md` gotcha, restated in this sprint's
own brief), every mechanic lands in one untagged turn unless a scenario
mints its own `turn_id` -- every scenario below does, including reusing one
`turn_id` across several refusals in AC1 (refusals never spend a turn, so
that is safe) and across the free moves, the free roll and the first real
action in AC3.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in one scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against `interact`
or `.errors` themselves -- this suite is red until they land, and green
once they do.
"""

import asyncio
import json
import os
import random as random_module

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service as playthrough_service

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

TO_THORNWAY = "to-thornway"  # village-green -> thornway
TO_LAIR_MAW = "to-lair-maw"  # thornway -> lair-maw
THORN_SCREEN_TEMPLATE = "thorn-screen"
BYPASS_ITEM = "shepherds-knife"  # the seed character's own carried item


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    and subclass the 07a/07b acceptance suites use, so a roll's `total` is
    a known number rather than a real one, and "meets the difficulty" can
    be asserted against a concrete number."""

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


async def _dm_tool_calls(
    session, run_id: str, *, result: str, name: str | None = "interact"
) -> list[dict]:
    """`tool_call` events at `dm` visibility, filtered to `result` and,
    unless `name` is `None`, to `name` (default `interact`, this file's own
    mechanic under test) -- the same run also carries `use_exit`'s own `ok`
    `tool_call` events (the walk to `lair-maw`), which must never be
    mistaken for one of `interact`'s. `name=None` fetches every mechanic's,
    for the one assertion that needs to see across them."""
    rows = (
        await session.execute(
            text(
                "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [
        p
        for p in (_payload(row) for row in rows)
        if p.get("result") == result and (name is None or p.get("name") == name)
    ]


class _second_connection:
    """An `AsyncSession` on its own connection to the same scratch
    database `playthrough_db` already pinned `DATABASE_URL` to -- never a
    session a refusing call itself ran on. The only way to read what is
    genuinely committed rather than merely flushed and still pending in
    the other session's open transaction (same helper as
    `test_acceptance_exits_and_endings.py` / `test_acceptance_rolls_spent_
    once.py`)."""

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


async def _objects_snapshot(session, run_id: str) -> list[tuple]:
    """Every `objects` row belonging to `run_id`, every column that could
    plausibly change under a mechanic's write -- not just the one fixture
    under test -- so "no object in the world changes" is checked against
    the whole world, not one row picked in advance."""
    rows = (
        await session.execute(
            text(
                "SELECT id, kind, template_id, name, member_id, owner_object_id, "
                "adventure_run_id, scene_id, current_hp, max_hp, armour_class, "
                "is_alive, state FROM objects WHERE campaign_run_id = :run_id ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return [tuple(row) for row in rows]


async def _object_id_by_template(session, run_id: str, template_id: str) -> str:
    row = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id"
            ),
            {"run_id": run_id, "template_id": template_id},
        )
    ).one()
    return row.id


async def _carried_object_id(session, *, owner_id: str, template_id: str) -> str:
    """The id of the `objects` row `owner_id` carries with `template_id` --
    the bypass check (I3) reports the *matching row's own id*, not the
    template string, as `outcome.bypassedBy`."""
    row = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner_id "
                "AND template_id = :template_id"
            ),
            {"owner_id": owner_id, "template_id": template_id},
        )
    ).one()
    return row.id


def _thorn_screen_checks():
    """The two authored checks on `thorn-screen`, picked by shape rather
    than index: the one with no `bypassed_by` at all, and the one bypassed
    by the seed character's own knife."""
    loaded = content_service.load_campaign(CAMPAIGN_ID, VERSION)
    thorn_screen = loaded.object_templates[THORN_SCREEN_TEMPLATE]
    no_bypass = next(c for c in thorn_screen.checks if not c.bypassed_by)
    bypassable = next(c for c in thorn_screen.checks if c.bypassed_by)
    assert BYPASS_ITEM in bypassable.bypassed_by
    return no_bypass, bypassable


def _strength_modifier() -> int:
    sheet = content_service.load_campaign(CAMPAIGN_ID, VERSION).campaign.seed_character
    return (sheet.abilities.strength - 10) // 2


async def _walk_to_lair_maw(db, *, user_id: str, actor_id: str) -> None:
    # `use_exit` takes no `turn_id` at all yet (its own docstring: "phase 8
    # adds one once a turn exists"), so every use lands in the untagged
    # turn regardless of when it is called -- exactly the free move AC3
    # exercises.
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_THORNWAY)
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_LAIR_MAW)


@pytest.mark.database
def test_ac1_interact_passes_by_roll_or_bypass_and_refuses_the_rest_untouched(playthrough_db):
    # <- AC1
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac1-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)
        await _walk_to_lair_maw(playthrough_db, user_id=owner_id, actor_id=character.id)

        thorn_screen_id = await _object_id_by_template(
            playthrough_db, run.id, THORN_SCREEN_TEMPLATE
        )
        lift_check, cut_check = _thorn_screen_checks()
        strength_modifier = _strength_modifier()

        # -- Refusal 1: an action the fixture's author never wrote. One
        # shared `turn_id` for every refusal below -- none of them spend
        # it (that is AC3's own rule, exercised for real there; relied on
        # here only to keep this scenario from minting a `turn_id` per
        # refusal).
        refusal_turn = generate_id()
        before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.raises(Exception) as unknown_action:
            await playthrough_service.interact(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                object_id=thorn_screen_id,
                action="Kick the screen down with brute strength",
                turn_id=refusal_turn,
            )
        assert unknown_action.value.code == ErrorCode.ACTION_NOT_AVAILABLE
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # -- Refusal 2: the check needs a roll (no `bypassed_by` at all)
        # and none was given.
        before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.raises(Exception) as missing_roll:
            await playthrough_service.interact(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                object_id=thorn_screen_id,
                action=lift_check.action,
                turn_id=refusal_turn,
            )
        assert missing_roll.value.code == ErrorCode.ROLL_REQUIRED
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # -- Refusal 3: the roll offered was made for something else -- an
        # `initiative` roll, never `ability_check`.
        wrong_kind_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="initiative",
            context={},
            face=10,
            turn_id=refusal_turn,
        )
        before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.raises(Exception) as wrong_kind:
            await playthrough_service.interact(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                object_id=thorn_screen_id,
                action=lift_check.action,
                roll_id=wrong_kind_roll.id,
                turn_id=refusal_turn,
            )
        assert wrong_kind.value.code == ErrorCode.ROLL_NOT_USABLE
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # Every refusal above genuinely persisted -- committed before its
        # `ApiError` was raised -- reachable from a connection that never
        # saw the attempts that wrote them, and visible to the DM only.
        async with _second_connection() as reader:
            refused = await _dm_tool_calls(reader, run.id, result="refused", name=None)
            assert len(refused) == 3
            assert {c["name"] for c in refused} == {"interact"}
            for call in refused:
                assert call["args"].get("actorId") == str(character.id)
                assert call["args"].get("objectId") == str(thorn_screen_id)
                assert call["outcome"], call
            actions_refused = [c["args"].get("action") for c in refused]
            assert actions_refused == [
                "Kick the screen down with brute strength",
                lift_check.action,
                lift_check.action,
            ]
            assert refused[2]["args"].get("rollId") == str(wrong_kind_roll.id)

        # -- Pass 1: bypassed by a carried item, no roll at all.
        bypass_turn = generate_id()
        before = await _objects_snapshot(playthrough_db, run.id)
        bypass_result = await playthrough_service.interact(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            object_id=thorn_screen_id,
            action=cut_check.action,
            turn_id=bypass_turn,
        )
        assert bypass_result is True
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        ok_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 1
        bypass_call = ok_calls[0]
        assert bypass_call["name"] == "interact"
        assert bypass_call["rollIds"] == []
        assert bypass_call["args"].get("actorId") == str(character.id)
        assert bypass_call["args"].get("objectId") == str(thorn_screen_id)
        assert bypass_call["args"].get("action") == cut_check.action
        assert bypass_call["outcome"]["action"] == cut_check.action
        assert bypass_call["outcome"]["dc"] == cut_check.dc
        knife_id = await _carried_object_id(
            playthrough_db, owner_id=character.id, template_id=BYPASS_ITEM
        )
        assert bypass_call["outcome"]["bypassedBy"] == str(knife_id)
        assert bypass_call["outcome"]["success"] is True

        # -- Pass 2, a fresh turn: a roll that meets (not exceeds) the
        # difficulty, no bypass involved -- the other check, which has no
        # `bypassed_by` at all, so only the roll can carry it.
        roll_turn = generate_id()
        face = lift_check.dc - strength_modifier
        assert 1 <= face <= 20, "seed character's strength pushed the needed face outside 1-20"
        r = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=face,
            turn_id=roll_turn,
        )
        total = face + strength_modifier
        assert total == lift_check.dc

        before = await _objects_snapshot(playthrough_db, run.id)
        roll_result = await playthrough_service.interact(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            object_id=thorn_screen_id,
            action=lift_check.action,
            roll_id=r.id,
            turn_id=roll_turn,
        )
        assert roll_result is True
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        ok_calls = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        assert len(ok_calls) == 2
        roll_call = next(c for c in ok_calls if c["rollIds"] == [str(r.id)])
        assert roll_call["args"].get("rollId") == str(r.id)
        assert roll_call["outcome"]["action"] == lift_check.action
        assert roll_call["outcome"]["dc"] == lift_check.dc
        assert roll_call["outcome"]["total"] == total
        assert roll_call["outcome"]["success"] is True
        assert "bypassedBy" not in roll_call["outcome"]

        # -- None of this -- pass or refusal -- reaches the player.
        player_events = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert not [e for e in player_events if e.type == "tool_call"]

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_one_action_per_creature_per_turn(playthrough_db):
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
        await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)

        lift_check, cut_check = _thorn_screen_checks()
        strength_modifier = _strength_modifier()

        # The untagged turn (`turn_id=None`, the only one that exists
        # before phase 8's allocator): `use_exit` takes no `turn_id`
        # parameter at all yet and always lands there, and a call that
        # passes no `turn_id` of its own lands there too -- exactly what
        # every one of the calls below does, on purpose, until the
        # scenario explicitly moves to a second turn below.

        # -- Things that are not actions -- using an exit, rolling -- spend
        # nothing, even inside the very turn an action is about to be
        # taken in.
        await _walk_to_lair_maw(playthrough_db, user_id=owner_id, actor_id=character.id)
        await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=1,
        )

        thorn_screen_id = await _object_id_by_template(playthrough_db, run.id, "thorn-screen")

        # -- A refused attempt first: it does not spend the turn either --
        # the real action right after it, in the very same (untagged)
        # turn, still succeeds.
        with pytest.raises(Exception) as first_refusal:
            await playthrough_service.interact(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                object_id=thorn_screen_id,
                action="Push through with brute strength",
            )
        assert first_refusal.value.code == ErrorCode.ACTION_NOT_AVAILABLE

        first_action = await playthrough_service.interact(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            object_id=thorn_screen_id,
            action=cut_check.action,
        )
        assert first_action is True

        # -- A second action by the same creature, same (untagged) turn,
        # is refused -- even a distinct, otherwise-valid action against
        # the same fixture.
        with pytest.raises(Exception) as second_action:
            await playthrough_service.interact(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                object_id=thorn_screen_id,
                action=lift_check.action,
            )
        assert second_action.value.code == ErrorCode.ALREADY_ACTED

        # -- Exactly one "ok" `tool_call` for this creature in this turn --
        # the count the rule is defined over.
        ok_calls_turn_a = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        actor_ok_turn_a = [
            c for c in ok_calls_turn_a if c["args"].get("actorId") == str(character.id)
        ]
        assert len(actor_ok_turn_a) == 1

        # -- A new turn allows the same creature to act again.
        turn_b = generate_id()
        face = lift_check.dc - strength_modifier
        assert 1 <= face <= 20, "seed character's strength pushed the needed face outside 1-20"
        r = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=face,
            turn_id=turn_b,
        )
        second_turn_action = await playthrough_service.interact(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            object_id=thorn_screen_id,
            action=lift_check.action,
            roll_id=r.id,
            turn_id=turn_b,
        )
        assert second_turn_action is True

        ok_calls_all = await _dm_tool_calls(playthrough_db, run.id, result="ok")
        actor_ok_all = [c for c in ok_calls_all if c["args"].get("actorId") == str(character.id)]
        assert len(actor_ok_all) == 2

    asyncio.run(_scenario())
