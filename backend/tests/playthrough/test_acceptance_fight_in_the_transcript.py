"""qa acceptance tests -- sprint 005/09 "a fight lives in the transcript"
(`docs/intents/005-game-state-services/sprints/09-fight-lives-in-the-
transcript/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`'s
new `attack`, `damage`, `roll_initiative` or `.errors`' new `HIT_NOT_USABLE`
-- those are this sprint's own work items, written in parallel, and this
file never reads them. Everything else driven here (`start_campaign_run`,
`create_character`, `enter_adventure`, `use_exit`, `roll`,
`request_player_roll`, `resolve_roll_request`) is earlier sprints', already
merged, used exactly as their own acceptance suites use them
(`test_acceptance_rolls_derived_and_recorded.py`,
`test_acceptance_rolls_spent_once.py`, `test_acceptance_interact_and_one_
action.py`). `app.modules.playthrough.dice` is read only to confirm the
seam (`_rng`) and the shape of `context` a roll's `kind` expects -- never
to learn anything about `attack`/`damage` themselves, which `dice.py`
does not implement.

Every scenario plays out against the shipped `greenhollow/v1` content
(`backend/content/campaigns/greenhollow/v1/`): the seed character (12 hp,
armour class 15, carrying a `shepherds-knife`) walks from `village-green`
through `to-thornway`/`to-lair-maw` into `lair-maw`, where three `goblin`
instances (armour class 13, 7 hp, a `Rusty Shortsword` at `to_hit +4`,
`1d6+2`) are already placed -- the same path and the same fixture scene
`test_acceptance_interact_and_one_action.py` and `test_acceptance_exits_
and_endings.py` use, read through `app.modules.content.service` rather
than pasted as literals, so this file survives an authored-content
change.

`dice._rng` is monkeypatched, scoped to `pytest.MonkeyPatch.context()` per
call, to a small scripted `random.Random` subclass (the same seam and
subclass every acceptance suite since 07a uses) so a roll's `total` and
`natural` face are known numbers, not real ones -- required here more than
anywhere else, since AC1 turns entirely on whether a total reaches an
armour class and whether a face came up a natural 20.

Every refusal's persisted `tool_call` record is read back from a
**second** connection to the same scratch database, opened only after the
refusing call has already raised -- never from the session that ran it,
for the same reason every earlier acceptance suite insists on this (a
flushed-but-uncommitted row is visible to the session that wrote it
regardless of whether the service ever committed).

AC4's schema-wide half asserts *exact sets*, not a blacklist of
suspicious-sounding words -- a table, a column or a `state` key either
belongs to the baseline this file captures for itself (the public schema's
tables and the `objects`/`events` columns, all fixed since migration
`0007`, none of which this sprint may add to; and whatever `objects.state`
already carries once a character exists and a scene is entered, before any
fight starts) or it does not exist at all. The only key this sprint is
allowed to add anywhere is `down`, on a character brought to zero.

With no turn allocator yet beyond what 08a introduced, a scenario that
needs a creature to act more than once mints a fresh `turn_id` per act
(`generate_id()`), exactly as `test_acceptance_interact_and_one_action.py`
does for its own AC3.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in one scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the
implementation itself -- this suite is red until `attack`, `damage` and
`roll_initiative` land, and green once they do.
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
from app.modules.playthrough import dice as playthrough_dice
from app.modules.playthrough import service as playthrough_service

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

VILLAGE_GREEN = "village-green"
LAIR_MAW = "lair-maw"
TO_THORNWAY = "to-thornway"  # village-green -> thornway
TO_LAIR_MAW = "to-lair-maw"  # thornway -> lair-maw

GOBLIN_TEMPLATE = "goblin"
KNIFE_TEMPLATE = "shepherds-knife"  # the seed character's own carried weapon
HORSESHOE_TEMPLATE = "bent-horseshoe"  # a floor item at village-green, carried by nobody

GOBLIN_ARMOUR_CLASS = 13
GOBLIN_MAX_HP = 7
GOBLIN_ATTACK = "Rusty Shortsword"
GOBLIN_TO_HIT = 4  # content's own stat block -- asserted, not assumed, in AC1
GOBLIN_DAMAGE_EXPR = "1d6+2"

CHARACTER_MAX_HP = 12
CHARACTER_ARMOUR_CLASS = 15
KNIFE_TO_HIT = 4
KNIFE_DAMAGE_EXPR = "1d4+2"

# The public schema's tables, fixed by migrations `0001`-`0007`
# (`backend/alembic/versions/`) -- this sprint adds none (its own `plan.md`:
# "no new columns; the fighting stats already exist"), so this is the exact
# set a whole fight must still find true.
EXPECTED_TABLES = {
    "users",
    "sessions",
    "srd_rules",
    "campaign_runs",
    "campaign_run_members",
    "adventure_runs",
    "objects",
    "events",
    "alembic_version",
}

# `objects`' own columns (`0005_objects.py`, unchanged since), read off
# `app.modules.playthrough.models.GameObject` -- reading the model is
# reading the shape of a table this sprint may not alter, not reading the
# sprint's new work.
EXPECTED_OBJECTS_COLUMNS = {
    "id",
    "campaign_run_id",
    "member_id",
    "kind",
    "template_id",
    "instance_key",
    "name",
    "source_adventure_id",
    "source_scene_id",
    "adventure_run_id",
    "scene_id",
    "owner_object_id",
    "current_hp",
    "max_hp",
    "armour_class",
    "is_alive",
    "state",
    "created_at",
    "updated_at",
}

# `events`' own columns (`0006_events.py`; `0007` only widens a check
# constraint's allowed values, adding no column).
EXPECTED_EVENTS_COLUMNS = {
    "id",
    "campaign_run_id",
    "actor_member_id",
    "turn_id",
    "type",
    "visibility",
    "payload",
    "prompt_tokens",
    "completion_tokens",
    "cost_usd",
    "created_at",
    "embedding",
    "embedding_model",
}

# Every key `objects.state` may ever carry, whole-run, character or
# creature alike: `CharacterState`'s own declared fields
# (`app.modules.playthrough.schemas.CharacterState`), `down` among them --
# declared and written `False` at character creation, never added later
# (only its *value* flips once a character is brought to zero, `AC2`'s own
# story). A template-born creature's `state` stays `{}` -- nothing this
# sprint's mechanics write to it -- so this exact set, not a delta, is what
# a whole fight must still find true (AC4): an encounter, a turn order or
# an `in_combat` flag, whatever it might be called, would show up here as
# an extra key.
EXPECTED_STATE_KEYS = {
    "abilities",
    "race",
    "character_class",
    "background",
    "appearance",
    "down",
    # sprint 009-02, WI2: a built sheet's full state, defaulted on the
    # seed-hero path this sprint still exercises.
    "level",
    "alignment",
    "speed",
    "proficiency_bonus",
    "saving_throws",
    "skills",
    "equipment",
}


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call -- the same seam
    and subclass every acceptance suite since 07a uses, so a roll's
    `total` and `natural` face are known numbers rather than real ones."""

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


def _state(row) -> dict:
    state = row.state
    if isinstance(state, str):
        state = json.loads(state)
    return state


class _second_connection:
    """An `AsyncSession` on its own connection to the same scratch
    database `playthrough_db` already pinned `DATABASE_URL` to -- never a
    session a refusing call itself ran on (same helper every acceptance
    suite since `test_acceptance_exits_and_endings.py` copies)."""

    async def __aenter__(self):
        self._engine = create_async_engine(os.environ["DATABASE_URL"])
        sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)
        self._session = sessionmaker()
        return self._session

    async def __aexit__(self, *exc_info) -> None:
        await self._session.close()
        await self._engine.dispose()


async def _rolled(db, *, user_id, actor_id, kind, context, face, turn_id=None, visibility="dm"):
    """Produces one real `roll` event through the 07a/07b producer `roll`,
    with `dice._rng` scripted for the duration of this call alone so the
    resulting `total`/`natural` face is a known number. Every formula this
    file needs (`1d20+-K`, `1dM+K`) is a single die, so one scripted face
    is always enough."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([face]))
        return await playthrough_service.roll(
            db,
            user_id=user_id,
            actor_id=actor_id,
            kind=kind,
            context=context,
            turn_id=turn_id,
            visibility=visibility,
        )


async def _tool_calls(session, run_id: str, *, name: str | None = None, result: str | None = None):
    """`tool_call` events at `dm` visibility (every mechanic in this
    module writes there, never to the player), each returned with its own
    event `id` merged into the payload -- `damage`'s `hit_id` names an
    `attack` `tool_call` by that very id."""
    rows = (
        await session.execute(
            text(
                "SELECT id, payload FROM events WHERE campaign_run_id = :run_id "
                "AND type = 'tool_call' AND visibility = 'dm' ORDER BY id"
            ),
            {"run_id": run_id},
        )
    ).all()
    calls = []
    for row in rows:
        payload = _payload(row)
        if name is not None and payload.get("name") != name:
            continue
        if result is not None and payload.get("result") != result:
            continue
        calls.append({"id": row.id, **payload})
    return calls


async def _object_ids_by_template(session, run_id: str, template_id: str, *, scene_id: str):
    rows = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id AND scene_id = :scene_id ORDER BY id"
            ),
            {"run_id": run_id, "template_id": template_id, "scene_id": scene_id},
        )
    ).all()
    return [row.id for row in rows]


async def _floor_object_id(session, run_id: str, template_id: str, *, scene_id: str):
    row = (
        await session.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id AND scene_id = :scene_id "
                "AND owner_object_id IS NULL"
            ),
            {"run_id": run_id, "template_id": template_id, "scene_id": scene_id},
        )
    ).one()
    return row.id


async def _carried_object_id(session, *, owner_id: str, template_id: str):
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


async def _object_row(session, object_id: str):
    return (
        await session.execute(
            text(
                "SELECT current_hp, max_hp, armour_class, is_alive, state "
                "FROM objects WHERE id = :id"
            ),
            {"id": object_id},
        )
    ).one()


async def _objects_snapshot(session, run_id: str) -> list[tuple]:
    """Every `objects` row belonging to `run_id`, every column that could
    plausibly change under a mechanic's write -- the same shape
    `test_acceptance_interact_and_one_action.py`'s own snapshot uses, so
    "no row changes" is checked against the whole world, not one row
    picked in advance."""
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


async def _state_keys(session, run_id: str) -> set[str]:
    """Every key that has ever been stored in *any* object's `state` for
    this run -- across the character and every creature alike, not one
    row picked in advance."""
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT jsonb_object_keys(state) AS key FROM objects "
                "WHERE campaign_run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    ).all()
    return {row.key for row in rows}


async def _table_names(session) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        )
    ).all()
    return {row.table_name for row in rows}


async def _column_names(session, table: str) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :table"
            ),
            {"table": table},
        )
    ).all()
    return {row.column_name for row in rows}


async def _walk_to_lair_maw(db, *, user_id: str, actor_id: str) -> None:
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_THORNWAY)
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_LAIR_MAW)


async def _setup_in_lair_maw(db, *, username: str):
    """A run, a character walked into `lair-maw`, and the three `goblin`
    instances already placed there -- the common opening every scenario in
    this file shares."""
    owner_id = generate_id()
    await _insert_user(db, owner_id, username=username)
    await db.commit()

    run = await playthrough_service.start_campaign_run(
        db, user_id=owner_id, campaign_id=CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(db, user_id=owner_id, run_id=run.id)
    await playthrough_service.enter_adventure(db, user_id=owner_id, run_id=run.id)
    await _walk_to_lair_maw(db, user_id=owner_id, actor_id=character.id)

    goblin_ids = await _object_ids_by_template(db, run.id, GOBLIN_TEMPLATE, scene_id=LAIR_MAW)
    assert len(goblin_ids) == 3, "greenhollow/v1's lair-maw placement changed under this test"

    knife_id = await _carried_object_id(db, owner_id=character.id, template_id=KNIFE_TEMPLATE)

    return owner_id, run, character, goblin_ids, knife_id


@pytest.mark.database
def test_ac1_attack_compares_the_roll_to_armour_and_refuses_the_rest(playthrough_db):
    # <- AC1
    async def _scenario():
        owner_id, run, character, goblin_ids, knife_id = await _setup_in_lair_maw(
            playthrough_db, username="ac1-owner"
        )
        goblin_id = goblin_ids[0]

        # -- A miss: total (5) short of the goblin's armour class (13).
        miss_turn = generate_id()
        miss_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=1,
            turn_id=miss_turn,
        )
        miss_outcome = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=miss_roll.id,
            turn_id=miss_turn,
        )
        assert miss_outcome == "miss"

        # -- A hit: total (13) exactly reaches the armour class, not a
        # natural 20.
        hit_turn = generate_id()
        hit_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=9,
            turn_id=hit_turn,
        )
        hit_outcome = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=hit_roll.id,
            turn_id=hit_turn,
        )
        assert hit_outcome == "hit"

        # -- A natural 20: a crit regardless of the armour it is measured
        # against -- the total (24) would already have hit on its own, so
        # only the outcome string itself, not a bare true/false, tells a
        # crit apart from a plain hit.
        crit_turn = generate_id()
        crit_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=20,
            turn_id=crit_turn,
        )
        crit_outcome = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=goblin_id,
            item_id=knife_id,
            roll_id=crit_roll.id,
            turn_id=crit_turn,
        )
        assert crit_outcome == "crit"

        ok_calls = await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
        assert len(ok_calls) == 3
        by_roll = {call["rollIds"][0]: call for call in ok_calls}

        miss_call = by_roll[str(miss_roll.id)]
        assert miss_call["args"] == {
            "actorId": str(character.id),
            "targetId": str(goblin_id),
            "itemId": str(knife_id),
            "rollId": str(miss_roll.id),
        }
        assert miss_call["outcome"]["outcome"] == "miss"
        assert miss_call["outcome"]["total"] == 1 + KNIFE_TO_HIT
        assert miss_call["outcome"]["natural"] == 1
        assert miss_call["outcome"]["armourClass"] == GOBLIN_ARMOUR_CLASS

        hit_call = by_roll[str(hit_roll.id)]
        assert hit_call["outcome"]["outcome"] == "hit"
        assert hit_call["outcome"]["total"] == 9 + KNIFE_TO_HIT
        assert hit_call["outcome"]["natural"] == 9
        assert hit_call["outcome"]["armourClass"] == GOBLIN_ARMOUR_CLASS

        crit_call = by_roll[str(crit_roll.id)]
        assert crit_call["outcome"]["outcome"] == "crit"
        assert crit_call["outcome"]["total"] == 20 + KNIFE_TO_HIT
        assert crit_call["outcome"]["natural"] == 20
        assert crit_call["outcome"]["armourClass"] == GOBLIN_ARMOUR_CLASS

        # -- Pass/fail is on the `tool_call`, never on the `roll` itself
        # (checked against the crit roll's own stored row).
        crit_roll_row = (
            await playthrough_db.execute(
                text("SELECT payload FROM events WHERE id = :id"), {"id": crit_roll.id}
            )
        ).one()
        crit_roll_payload = _payload(crit_roll_row)
        assert "outcome" not in crit_roll_payload
        assert "armourClass" not in crit_roll_payload
        assert "success" not in crit_roll_payload

        # -- None of this reaches the goblin's own hit points: AC1 never
        # applies damage.
        goblin_row = await _object_row(playthrough_db, goblin_id)
        assert goblin_row.current_hp == GOBLIN_MAX_HP
        assert goblin_row.is_alive is True

        # -- Refusals, one shared turn (none of them succeed, so none
        # spend it -- `test_acceptance_interact_and_one_action.py`'s own
        # AC1 relies on the same rule).
        refusal_turn = generate_id()

        # A target standing in another scene: the character is at
        # `lair-maw`, the well-known "somewhere else" object is the
        # untouched floor item at `village-green` -- but the target of an
        # attack must itself be reachable, so this uses a goblin id from a
        # scene the actor has already left behind: none exist yet, so the
        # actor instead attacks from `village-green` before ever walking,
        # using a fresh run of its own so the earlier hits above are
        # undisturbed.
        elsewhere_owner_id = generate_id()
        await _insert_user(playthrough_db, elsewhere_owner_id, username="ac1-elsewhere")
        await playthrough_db.commit()
        elsewhere_run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=elsewhere_owner_id, campaign_id=CAMPAIGN_ID
        )
        elsewhere_character = await playthrough_service.create_character(
            playthrough_db, user_id=elsewhere_owner_id, run_id=elsewhere_run.id
        )
        await playthrough_service.enter_adventure(
            playthrough_db, user_id=elsewhere_owner_id, run_id=elsewhere_run.id
        )
        elsewhere_goblin_id = (
            await _object_ids_by_template(
                playthrough_db, elsewhere_run.id, GOBLIN_TEMPLATE, scene_id=LAIR_MAW
            )
        )[0]
        elsewhere_knife_id = await _carried_object_id(
            playthrough_db, owner_id=elsewhere_character.id, template_id=KNIFE_TEMPLATE
        )
        elsewhere_roll = await _rolled(
            playthrough_db,
            user_id=elsewhere_owner_id,
            actor_id=elsewhere_character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=refusal_turn,
        )
        before = await _objects_snapshot(playthrough_db, elsewhere_run.id)
        with pytest.raises(Exception) as elsewhere_exc:
            await playthrough_service.attack(
                playthrough_db,
                user_id=elsewhere_owner_id,
                actor_id=elsewhere_character.id,
                target_id=elsewhere_goblin_id,  # still in lair-maw; the actor never walked there
                item_id=elsewhere_knife_id,
                roll_id=elsewhere_roll.id,
                turn_id=refusal_turn,
            )
        assert elsewhere_exc.value.code == ErrorCode.OBJECT_NOT_REACHABLE
        after = await _objects_snapshot(playthrough_db, elsewhere_run.id)
        assert after == before

        # A weapon the actor is not carrying: the untouched floor item at
        # `village-green` -- the main character and goblin are in the same
        # scene, so only the item-carried check can be the cause.
        horseshoe_id = await _floor_object_id(
            playthrough_db, run.id, HORSESHOE_TEMPLATE, scene_id=VILLAGE_GREEN
        )
        unheld_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=15,
            turn_id=refusal_turn,
        )
        before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.raises(Exception) as unheld_exc:
            await playthrough_service.attack(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=horseshoe_id,
                roll_id=unheld_roll.id,
                turn_id=refusal_turn,
            )
        assert unheld_exc.value.code == ErrorCode.OBJECT_NOT_REACHABLE
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # A roll made for something else -- an `ability_check`, never
        # `attack`.
        wrong_kind_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "strength"},
            face=15,
            turn_id=refusal_turn,
        )
        before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.raises(Exception) as wrong_kind_exc:
            await playthrough_service.attack(
                playthrough_db,
                user_id=owner_id,
                actor_id=character.id,
                target_id=goblin_id,
                item_id=knife_id,
                roll_id=wrong_kind_roll.id,
                turn_id=refusal_turn,
            )
        assert wrong_kind_exc.value.code == ErrorCode.ROLL_NOT_USABLE
        after = await _objects_snapshot(playthrough_db, run.id)
        assert after == before

        # Every refusal above genuinely persisted -- committed before its
        # `ApiError` was raised -- reachable from a connection that never
        # saw the attempts that wrote them.
        async with _second_connection() as reader:
            refused_main = await _tool_calls(reader, run.id, name="attack", result="refused")
            assert len(refused_main) == 2  # the unheld weapon and the wrong roll kind
            for call in refused_main:
                assert call["outcome"], call
            refused_elsewhere = await _tool_calls(
                reader, elsewhere_run.id, name="attack", result="refused"
            )
            assert len(refused_elsewhere) == 1
            assert refused_elsewhere[0]["outcome"], refused_elsewhere[0]

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac2_damage_is_bound_to_the_hit_that_landed_it(playthrough_db):
    # <- AC2
    async def _scenario():
        owner_id, run, character, goblin_ids, knife_id = await _setup_in_lair_maw(
            playthrough_db, username="ac2-owner"
        )
        target_goblin, miss_goblin = goblin_ids[0], goblin_ids[1]

        # `down` starts `False` at character creation -- the observable
        # this AC's own damage-at-zero story flips, later, to `True`.
        assert _state(await _object_row(playthrough_db, character.id))["down"] is False

        # -- Turn 1: a hit against `target_goblin`, then damage bound to
        # it -- lowering current_hp without clamping yet.
        turn1 = generate_id()
        hit1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=9,  # total 13, exactly the armour class -- a hit
            turn_id=turn1,
        )
        outcome1 = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=target_goblin,
            item_id=knife_id,
            roll_id=hit1_roll.id,
            turn_id=turn1,
        )
        assert outcome1 == "hit"
        hit1 = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(hit1_roll.id)]
        )
        hit1_id = hit1["id"]

        # A `hit_id` from another turn is refused before it is ever
        # spent -- the roll offered alongside it is otherwise entirely
        # valid.
        other_turn = generate_id()
        stray_damage_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=other_turn,
        )
        before = await _object_row(playthrough_db, target_goblin)
        with pytest.raises(Exception) as wrong_turn_exc:
            await playthrough_service.damage(
                playthrough_db,
                user_id=owner_id,
                target_id=target_goblin,
                roll_id=stray_damage_roll.id,
                hit_id=hit1_id,
                turn_id=other_turn,
            )
        assert wrong_turn_exc.value.code == ErrorCode.HIT_NOT_USABLE
        after = await _object_row(playthrough_db, target_goblin)
        assert after.current_hp == before.current_hp

        # The genuine damage call, same turn as the hit: rolled 6, applied
        # 6 (well under the goblin's remaining 7).
        damage1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,  # total 6
            turn_id=turn1,
        )
        applied1 = await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=target_goblin,
            roll_id=damage1_roll.id,
            hit_id=hit1_id,
            turn_id=turn1,
        )
        assert applied1 == 6
        after_damage1 = await _object_row(playthrough_db, target_goblin)
        assert after_damage1.current_hp == GOBLIN_MAX_HP - 6 == 1
        assert after_damage1.is_alive is True

        damage1_call = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="damage", result="ok")
            if c["rollIds"] == [str(damage1_roll.id)]
        )
        assert damage1_call["args"] == {
            "targetId": str(target_goblin),
            "rollId": str(damage1_roll.id),
            "hitId": str(hit1_id),
        }
        assert damage1_call["outcome"]["rolled"] == 6
        assert damage1_call["outcome"]["applied"] == 6
        assert damage1_call["outcome"]["currentHp"] == 1
        assert damage1_call["outcome"]["isAlive"] is True

        # The same `hit_id`, spent a second time, is refused.
        redo_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=1,
            turn_id=turn1,
        )
        before = await _object_row(playthrough_db, target_goblin)
        with pytest.raises(Exception) as double_spend_exc:
            await playthrough_service.damage(
                playthrough_db,
                user_id=owner_id,
                target_id=target_goblin,
                roll_id=redo_roll.id,
                hit_id=hit1_id,
                turn_id=turn1,
            )
        assert double_spend_exc.value.code == ErrorCode.HIT_NOT_USABLE
        after = await _object_row(playthrough_db, target_goblin)
        assert after.current_hp == before.current_hp

        # -- Turn 2: a second hit against the same goblin, then damage
        # clamped at zero (rolled 6 against a remaining 1) -- a
        # member-less creature at zero is no longer alive.
        turn2 = generate_id()
        hit2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=9,
            turn_id=turn2,
        )
        outcome2 = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=target_goblin,
            item_id=knife_id,
            roll_id=hit2_roll.id,
            turn_id=turn2,
        )
        assert outcome2 == "hit"
        hit2_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(hit2_roll.id)]
        )["id"]

        damage2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,  # total 6, more than the remaining 1
            turn_id=turn2,
        )
        applied2 = await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=target_goblin,
            roll_id=damage2_roll.id,
            hit_id=hit2_id,
            turn_id=turn2,
        )
        assert applied2 == 1  # clamped: rolled 6, only 1 hp remained
        after_damage2 = await _object_row(playthrough_db, target_goblin)
        assert after_damage2.current_hp == 0
        assert after_damage2.is_alive is False

        damage2_call = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="damage", result="ok")
            if c["rollIds"] == [str(damage2_roll.id)]
        )
        assert damage2_call["outcome"]["rolled"] == 6
        assert damage2_call["outcome"]["applied"] == 1
        assert damage2_call["outcome"]["currentHp"] == 0
        assert damage2_call["outcome"]["isAlive"] is False

        # -- A `hit_id` naming a miss is refused: `miss_goblin` is
        # attacked and missed, then damage against it is attempted.
        turn3 = generate_id()
        miss_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=1,  # total 5, short of 13 -- a miss
            turn_id=turn3,
        )
        miss_outcome = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=miss_goblin,
            item_id=knife_id,
            roll_id=miss_roll.id,
            turn_id=turn3,
        )
        assert miss_outcome == "miss"
        miss_hit_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(miss_roll.id)]
        )["id"]

        against_miss_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=turn3,
        )
        before = await _object_row(playthrough_db, miss_goblin)
        with pytest.raises(Exception) as against_miss_exc:
            await playthrough_service.damage(
                playthrough_db,
                user_id=owner_id,
                target_id=miss_goblin,
                roll_id=against_miss_roll.id,
                hit_id=miss_hit_id,
                turn_id=turn3,
            )
        assert against_miss_exc.value.code == ErrorCode.HIT_NOT_USABLE
        after = await _object_row(playthrough_db, miss_goblin)
        assert after.current_hp == before.current_hp == GOBLIN_MAX_HP
        assert after.is_alive is True

        # -- A character brought to zero stays alive and goes down
        # instead: two goblin hits against the character.
        turn4 = generate_id()
        goblin_hit1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=miss_goblin,
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,  # total 15, exactly the character's armour class
            turn_id=turn4,
        )
        goblin_outcome1 = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=miss_goblin,
            target_id=character.id,
            roll_id=goblin_hit1_roll.id,
            turn_id=turn4,
        )
        assert goblin_outcome1 == "hit"
        goblin_hit1_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(goblin_hit1_roll.id)]
        )["id"]
        goblin_damage1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=miss_goblin,
            kind="damage",
            context={"attack": GOBLIN_ATTACK},
            face=6,  # total 8
            turn_id=turn4,
        )
        applied_to_char1 = await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=character.id,
            roll_id=goblin_damage1_roll.id,
            hit_id=goblin_hit1_id,
            turn_id=turn4,
        )
        assert applied_to_char1 == 8
        after_char1 = await _object_row(playthrough_db, character.id)
        assert after_char1.current_hp == CHARACTER_MAX_HP - 8 == 4
        assert after_char1.is_alive is True
        assert _state(after_char1)["down"] is False

        turn5 = generate_id()
        goblin_hit2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_ids[2],
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,
            turn_id=turn5,
        )
        goblin_outcome2 = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_ids[2],
            target_id=character.id,
            roll_id=goblin_hit2_roll.id,
            turn_id=turn5,
        )
        assert goblin_outcome2 == "hit"
        goblin_hit2_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(goblin_hit2_roll.id)]
        )["id"]
        goblin_damage2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_ids[2],
            kind="damage",
            context={"attack": GOBLIN_ATTACK},
            face=6,  # total 8, more than the remaining 4
            turn_id=turn5,
        )
        applied_to_char2 = await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=character.id,
            roll_id=goblin_damage2_roll.id,
            hit_id=goblin_hit2_id,
            turn_id=turn5,
        )
        assert applied_to_char2 == 4  # clamped: rolled 8, only 4 hp remained
        after_char2 = await _object_row(playthrough_db, character.id)
        assert after_char2.current_hp == 0
        assert after_char2.is_alive is True  # a character never becomes not-alive here
        assert _state(after_char2)["down"] is True

        damage_to_char2_call = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="damage", result="ok")
            if c["rollIds"] == [str(goblin_damage2_roll.id)]
        )
        assert damage_to_char2_call["outcome"]["applied"] == 4
        assert damage_to_char2_call["outcome"]["currentHp"] == 0
        assert damage_to_char2_call["outcome"]["isAlive"] is True
        assert damage_to_char2_call["outcome"]["down"] is True

        # Every refusal above genuinely persisted.
        async with _second_connection() as reader:
            refused = await _tool_calls(reader, run.id, name="damage", result="refused")
            assert len(refused) == 3
            for call in refused:
                assert call["outcome"], call

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac3_one_attack_per_turn_and_a_monster_needs_no_player_roll(playthrough_db):
    # <- AC3
    async def _scenario():
        owner_id, run, character, goblin_ids, knife_id = await _setup_in_lair_maw(
            playthrough_db, username="ac3-owner"
        )
        goblin_id = goblin_ids[0]

        # -- A goblin's whole turn: roll, attack, damage -- driven directly
        # by the DM, never through `request_player_roll`.
        turn = generate_id()
        attack_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_id,
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,  # total 15, exactly the character's armour class
            turn_id=turn,
        )
        outcome = await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_id,
            target_id=character.id,
            roll_id=attack_roll.id,
            turn_id=turn,
        )
        assert outcome == "hit"

        # -- A second attack by the very same creature, same turn, is
        # refused -- even against a different, otherwise-valid target.
        second_target = goblin_ids[1]
        second_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_id,
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,
            turn_id=turn,
        )
        with pytest.raises(Exception) as second_attack_exc:
            await playthrough_service.attack(
                playthrough_db,
                user_id=owner_id,
                actor_id=goblin_id,
                target_id=second_target,
                roll_id=second_roll.id,
                turn_id=turn,
            )
        assert second_attack_exc.value.code == ErrorCode.ALREADY_ACTED

        # -- The turn's wound, bound to the hit that landed it -- completed
        # without ever asking the player to roll.
        hit_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(attack_roll.id)]
        )["id"]
        damage_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_id,
            kind="damage",
            context={"attack": GOBLIN_ATTACK},
            face=6,
            turn_id=turn,
        )
        applied = await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=character.id,
            roll_id=damage_roll.id,
            hit_id=hit_id,
            turn_id=turn,
        )
        assert applied == 8
        after = await _object_row(playthrough_db, character.id)
        assert after.current_hp == CHARACTER_MAX_HP - 8

        # -- Nowhere in this whole monster turn was the player asked to
        # roll: every `roll_requested` in the run stayed at `dm`
        # visibility (`roll`'s own outright pair), never `player`'s.
        player_requests = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'roll_requested' AND visibility = 'player'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert player_requests == []

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4_initiative_rolls_and_no_fight_is_ever_stored(playthrough_db):
    # <- AC4
    async def _scenario():
        owner_id, run, character, goblin_ids, knife_id = await _setup_in_lair_maw(
            playthrough_db, username="ac4-owner"
        )

        # -- The schema's own shape, and every key `objects.state` has
        # ever carried, already exactly the expected set before any fight
        # mechanic runs -- `down` is a character-state field declared and
        # written `False` at creation, not something combat adds.
        assert await _table_names(playthrough_db) == EXPECTED_TABLES
        assert await _column_names(playthrough_db, "objects") == EXPECTED_OBJECTS_COLUMNS
        assert await _column_names(playthrough_db, "events") == EXPECTED_EVENTS_COLUMNS
        assert await _state_keys(playthrough_db, run.id) == EXPECTED_STATE_KEYS

        # -- Rolling for who goes first: exactly two `roll(initiative)`
        # events, and not one row of the world changes.
        objects_before = await _objects_snapshot(playthrough_db, run.id)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([15]))
            event_a, event_b = await playthrough_service.roll_initiative(
                playthrough_db,
                user_id=owner_id,
                side_a_ids=[character.id],
                side_b_ids=goblin_ids,
            )
        types = {event_a.type, event_b.type}
        assert types == {"roll_requested", "roll"}, "side_a has a member; side_b does not"
        requested_event = event_a if event_a.type == "roll_requested" else event_b
        outright_event = event_b if event_a.type == "roll_requested" else event_a

        outright_row = (
            await playthrough_db.execute(
                text("SELECT visibility, payload FROM events WHERE id = :id"),
                {"id": outright_event.id},
            )
        ).one()
        assert outright_row.visibility == "player"
        assert _payload(outright_row)["kind"] == "initiative"

        requested_row = (
            await playthrough_db.execute(
                text("SELECT visibility, payload FROM events WHERE id = :id"),
                {"id": requested_event.id},
            )
        ).one()
        assert requested_row.visibility == "player"
        assert _payload(requested_row)["kind"] == "initiative"

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(playthrough_dice, "_rng", lambda: _ScriptedRandom([10]))
            answered = await playthrough_service.resolve_roll_request(
                playthrough_db, user_id=owner_id, request_id=requested_event.id
            )
        assert answered.type == "roll"

        initiative_rolls = (
            await playthrough_db.execute(
                text(
                    "SELECT id FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'roll' AND payload->>'kind' = 'initiative'"
                ),
                {"run_id": run.id},
            )
        ).all()
        assert len(initiative_rolls) == 2

        objects_after = await _objects_snapshot(playthrough_db, run.id)
        assert objects_after == objects_before

        # -- A whole fight, played out: the character kills one goblin,
        # a second goblin brings the character down.
        goblin_to_kill, goblin_to_fight_back = goblin_ids[0], goblin_ids[1]

        turn1 = generate_id()
        hit1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=9,
            turn_id=turn1,
        )
        await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=goblin_to_kill,
            item_id=knife_id,
            roll_id=hit1_roll.id,
            turn_id=turn1,
        )
        hit1_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(hit1_roll.id)]
        )["id"]
        damage1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=turn1,
        )
        await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=goblin_to_kill,
            roll_id=damage1_roll.id,
            hit_id=hit1_id,
            turn_id=turn1,
        )

        turn2 = generate_id()
        hit2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="attack",
            context={"item_id": KNIFE_TEMPLATE},
            face=9,
            turn_id=turn2,
        )
        await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            target_id=goblin_to_kill,
            item_id=knife_id,
            roll_id=hit2_roll.id,
            turn_id=turn2,
        )
        hit2_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(hit2_roll.id)]
        )["id"]
        damage2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="damage",
            context={"item_id": KNIFE_TEMPLATE},
            face=4,
            turn_id=turn2,
        )
        await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=goblin_to_kill,
            roll_id=damage2_roll.id,
            hit_id=hit2_id,
            turn_id=turn2,
        )
        killed = await _object_row(playthrough_db, goblin_to_kill)
        assert killed.is_alive is False

        turn3 = generate_id()
        gh1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,
            turn_id=turn3,
        )
        await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            target_id=character.id,
            roll_id=gh1_roll.id,
            turn_id=turn3,
        )
        gh1_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(gh1_roll.id)]
        )["id"]
        gd1_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            kind="damage",
            context={"attack": GOBLIN_ATTACK},
            face=6,
            turn_id=turn3,
        )
        await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=character.id,
            roll_id=gd1_roll.id,
            hit_id=gh1_id,
            turn_id=turn3,
        )

        turn4 = generate_id()
        gh2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            kind="attack",
            context={"attack": GOBLIN_ATTACK},
            face=11,
            turn_id=turn4,
        )
        await playthrough_service.attack(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            target_id=character.id,
            roll_id=gh2_roll.id,
            turn_id=turn4,
        )
        gh2_id = next(
            c
            for c in await _tool_calls(playthrough_db, run.id, name="attack", result="ok")
            if c["rollIds"] == [str(gh2_roll.id)]
        )["id"]
        gd2_roll = await _rolled(
            playthrough_db,
            user_id=owner_id,
            actor_id=goblin_to_fight_back,
            kind="damage",
            context={"attack": GOBLIN_ATTACK},
            face=6,
            turn_id=turn4,
        )
        await playthrough_service.damage(
            playthrough_db,
            user_id=owner_id,
            target_id=character.id,
            roll_id=gd2_roll.id,
            hit_id=gh2_id,
            turn_id=turn4,
        )
        downed = await _object_row(playthrough_db, character.id)
        assert downed.current_hp == 0
        assert downed.is_alive is True
        assert _state(downed)["down"] is True

        # -- After a whole fight has been played out: the exact same
        # tables and columns, and `state`'s own key set still exactly the
        # expected one -- never an encounter, a turn order or an
        # `in_combat` flag, whatever it might be called, on any object.
        assert await _table_names(playthrough_db) == EXPECTED_TABLES
        assert await _column_names(playthrough_db, "objects") == EXPECTED_OBJECTS_COLUMNS
        assert await _column_names(playthrough_db, "events") == EXPECTED_EVENTS_COLUMNS
        assert await _state_keys(playthrough_db, run.id) == EXPECTED_STATE_KEYS

    asyncio.run(_scenario())
