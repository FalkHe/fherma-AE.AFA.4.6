"""sprint 011/04 WI1 -- `service.get_situation` and `Situation.public()`
(`docs/intents/011-game-flow/sprints/04-situation-and-memory/`).

Driven against the real shipped `greenhollow/v1` content, the same pattern
`test_acceptance_table_read_for_play_screen.py` and
`test_acceptance_interact_and_one_action.py` use: `start_campaign_run`,
`create_character`, `enter_adventure` and `use_exit` walk the seed
character `village-green -> thornway -> lair-maw`, where three goblins and
the `thorn-screen` fixture are placed. The fixture's strength check is
opened by its own `bypassed_by` (the seed character's carried
`shepherds-knife` -- no roll needed), giving a real, persisted
`fixture_outcomes` entry. One goblin is marked hostile through
`set_hostility` so a `hostile` role has a concrete source to assert
against; the other two are left alone; the whole path also leaves a
handful of real `scene_entered`/`way_opened` events in the transcript for
`recent`.

`lair-maw`'s own `to-lair-hollow` exit carries no authored condition, so
`content_service.load_campaign` is monkeypatched, once the world is
already built from the *real* content, to answer a copy of the same
`LoadedCampaign` with a condition spliced onto that one exit -- the
monkeypatch never touches `start_campaign_run`'s own placement, which
already ran. `lair-maw` authors no `pressure` either; that field is
asserted `None` rather than forced, since no shipped scene ever sets it.

No `pytest-asyncio` (`AGENTS.md` gotchas): every scenario below wraps its
async calls in one `asyncio.run(...)`.
"""

import asyncio
import dataclasses

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.content.schemas import LoadedCampaign
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import SituationError
from app.modules.playthrough.models import GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

TO_THORNWAY = "to-thornway"
TO_LAIR_MAW = "to-lair-maw"
MIRA_TEMPLATE = "mira"
KNIFE_TEMPLATE = "shepherds-knife"
LAIR_MAW_EXIT = "to-lair-hollow"
INJECTED_CONDITION = "the goblins have already been dealt with"
FIXTURE_BYPASSED_ACTION = "Cut through the lashings that hold the screen together"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


def _with_injected_condition(loaded: LoadedCampaign) -> LoadedCampaign:
    scene = loaded.scenes["lair-maw"]
    new_exits = [
        exit_.model_copy(update={"condition": INJECTED_CONDITION})
        if exit_.id == LAIR_MAW_EXIT
        else exit_
        for exit_ in scene.exits
    ]
    new_scene = scene.model_copy(update={"exits": new_exits})
    new_scenes = {**loaded.scenes, "lair-maw": new_scene}
    return loaded.model_copy(update={"scenes": new_scenes})


async def _give_knife(db, *, user_id: str, run_id: str, character_id: str) -> None:
    """Mira hands her shepherd's knife to the hero, exactly as
    `village-green`'s own content has her do -- the seed pack no longer
    carries one of its own. Must run before the actor leaves
    `village-green`: `give` never reaches across scenes."""
    mira_id = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE campaign_run_id = :run_id "
                "AND template_id = :template_id"
            ),
            {"run_id": run_id, "template_id": MIRA_TEMPLATE},
        )
    ).scalar_one()
    knife_id = (
        await db.execute(
            text(
                "SELECT id FROM objects WHERE owner_object_id = :owner "
                "AND template_id = :template_id"
            ),
            {"owner": mira_id, "template_id": KNIFE_TEMPLATE},
        )
    ).scalar_one()
    await playthrough_service.give(
        db, user_id=user_id, from_id=mira_id, to_id=character_id, item_id=knife_id
    )


async def _walk_to_lair_maw(db, *, user_id: str, run_id: str, actor_id: str) -> None:
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_THORNWAY)
    await playthrough_service.use_exit(db, user_id=user_id, actor_id=actor_id, exit_id=TO_LAIR_MAW)


async def _scene_objects(db, *, run_id: str, scene_id: str, kind: str) -> list[GameObject]:
    from sqlalchemy import select

    result = await db.execute(
        select(GameObject).where(
            GameObject.campaign_run_id == run_id,
            GameObject.scene_id == scene_id,
            GameObject.kind == kind,
            GameObject.owner_object_id.is_(None),
        )
    )
    return list(result.scalars().all())


@pytest.mark.database
def test_a_rich_scene_populates_every_field(playthrough_db, monkeypatch):
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="situation-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        adventure_run = await playthrough_service.enter_adventure(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        await _give_knife(
            playthrough_db, user_id=owner_id, run_id=run.id, character_id=character.id
        )
        await _walk_to_lair_maw(
            playthrough_db, user_id=owner_id, run_id=run.id, actor_id=character.id
        )

        fixtures = await _scene_objects(
            playthrough_db, run_id=run.id, scene_id="lair-maw", kind="fixture"
        )
        assert len(fixtures) == 1
        fixture = fixtures[0]

        goblins = [
            obj
            for obj in await _scene_objects(
                playthrough_db, run_id=run.id, scene_id="lair-maw", kind="creature"
            )
            if obj.id != character.id
        ]
        assert len(goblins) == 3

        interact_result = await playthrough_service.interact(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            object_id=fixture.id,
            action=FIXTURE_BYPASSED_ACTION,
        )
        assert interact_result.status == "ok"

        await playthrough_service.set_hostility(
            playthrough_db, user_id=owner_id, actor_id=goblins[0].id, hostile=True
        )

        real_loaded = content_service.load_campaign(CAMPAIGN_ID, VERSION)
        patched_loaded = _with_injected_condition(real_loaded)
        monkeypatch.setattr(
            content_service, "load_campaign", lambda *args, **kwargs: patched_loaded
        )

        situation = await playthrough_service.get_situation(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        assert situation.run_id == run.id
        assert situation.hero_id == character.id
        assert situation.adventure_run_id == adventure_run.id
        assert situation.scene_id == "lair-maw"
        assert situation.campaign_title == "Greenhollow"
        assert situation.adventure_title == "Goblins of Greenhollow"
        assert situation.scene_title == "The Lair Maw"
        assert situation.truth and all(isinstance(line, str) for line in situation.truth)
        assert situation.consequences
        assert situation.pressure is None  # never authored in this campaign
        assert situation.npc_intent is not None and "goblins" in situation.npc_intent.lower()

        assert len(situation.secrets) == 1
        secret = situation.secrets[0]
        assert secret.ability == "wisdom"
        assert secret.skill == "Perception"
        assert secret.dc == 14
        assert "second, smaller gap" in secret.fact

        assert situation.hero.id == character.id
        assert situation.hero.role == "hero"
        assert situation.hero.current_hp == character.max_hp

        assert len(situation.actors) == 3
        assert {actor.id for actor in situation.actors} == {g.id for g in goblins}
        hostile_actor = next(actor for actor in situation.actors if actor.id == goblins[0].id)
        assert hostile_actor.role == "hostile"
        assert hostile_actor.hostile is True
        assert hostile_actor.attacks  # goblin stat block carries named attacks
        assert hostile_actor.disposition is not None

        assert len(situation.fixtures) == 1
        fixture_view = situation.fixtures[0]
        assert fixture_view.id == fixture.id
        assert fixture_view.name == "Screen of Thornbrush"
        assert len(fixture_view.checks) == 2
        assert all(check.dc for check in fixture_view.checks)
        assert fixture_view.outcomes.get(FIXTURE_BYPASSED_ACTION) == (
            "The screen sags open and the cave mouth stands clear; "
            "anything watching the entrance sees it happen."
        )

        assert len(situation.exits) == 1
        exit_view = situation.exits[0]
        assert exit_view.id == LAIR_MAW_EXIT
        assert exit_view.condition == INJECTED_CONDITION

        assert situation.recent
        assert all(event.type != "tool_call" for event in situation.recent)  # dm-only, excluded
        ids = [event.id for event in situation.recent]
        assert ids == sorted(ids)  # oldest first

        # -- public() carries no secret, dc, ability, skill or npc_intent --
        public = situation.public()
        assert not hasattr(public, "secrets")
        assert not hasattr(public, "npc_intent")
        for fixture_view in public.fixtures:
            assert fixture_view.checks == ()
            assert fixture_view.outcomes.get(FIXTURE_BYPASSED_ACTION)  # recorded fact survives

        def _walk(value, path):
            if dataclasses.is_dataclass(value) and not isinstance(value, type):
                for f in dataclasses.fields(value):
                    assert f.name not in ("ability", "skill", "dc", "npc_intent", "secrets"), (
                        f"leaked private field {f.name!r} at {path}"
                    )
                    _walk(getattr(value, f.name), f"{path}.{f.name}")
            elif isinstance(value, (list, tuple)):
                for i, item in enumerate(value):
                    _walk(item, f"{path}[{i}]")
            elif isinstance(value, dict):
                for k, v in value.items():
                    _walk(v, f"{path}.{k}")

        _walk(public, "public")

    asyncio.run(_scenario())


@pytest.mark.database
def test_an_armed_stranger_defaults_hostile_and_an_unarmed_one_neutral(playthrough_db):
    # <- AC1, verifier round 1: neither goblin disposition names hostility
    # in its prose (only cowardice and ruthlessness), so the default must
    # arm them regardless -- and `mira`, the unarmed innkeeper, must stay
    # `neutral` with no `set_hostility` call at all on either side.
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="situation-default-role")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)

        village_green = await playthrough_service.get_situation(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        mira = next(actor for actor in village_green.actors if actor.name == "Mira")
        assert mira.attacks == ()
        assert mira.role == "neutral"
        assert mira.hostile is False

        await _walk_to_lair_maw(
            playthrough_db, user_id=owner_id, run_id=run.id, actor_id=character.id
        )

        lair_maw = await playthrough_service.get_situation(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert len(lair_maw.actors) == 3
        for goblin in lair_maw.actors:
            assert goblin.attacks
            assert goblin.role == "hostile"
            assert goblin.hostile is True

    asyncio.run(_scenario())


@pytest.mark.database
def test_a_broken_scene_reference_raises(playthrough_db):
    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="situation-broken")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        await playthrough_service.enter_adventure(playthrough_db, user_id=owner_id, run_id=run.id)

        character.scene_id = "no-such-scene"
        await playthrough_db.commit()

        with pytest.raises(SituationError):
            await playthrough_service.get_situation(playthrough_db, user_id=owner_id, run_id=run.id)

    asyncio.run(_scenario())
