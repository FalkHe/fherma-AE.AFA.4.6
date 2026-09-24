"""WI2 (sprint 011/01): an authored `Secret`/`FixtureCheck`'s ability, skill
and DC drive an active check request, a passive check and a saving throw --
never anything parsed from its prose (AC3). `authored_check` is engine-free;
the formula it feeds `dice.derive_formula` is exercised the same way
`test_dice.py` does, and the passive check's own event is exercised the
same way `test_service_rolls.py`'s database tests are.
"""

import asyncio

import pytest
from sqlalchemy import text

from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.content.schemas import FixtureCheck, Secret
from app.modules.playthrough import dice, service
from app.modules.playthrough.models import GameObject

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

_ABILITIES = {
    "strength": 8,
    "dexterity": 12,
    "constitution": 10,
    "intelligence": 14,
    "wisdom": 16,
    "charisma": 10,
}


def _character() -> GameObject:
    return GameObject(
        campaign_run_id="run-1",
        kind="creature",
        template_id=None,
        instance_key="pc:member-1:1",
        name="Fixture Hero",
        state={"abilities": _ABILITIES},
    )


def _secret(**overrides) -> Secret:
    fields = {
        "fact": "the door is trapped",
        "ability": "wisdom",
        "dc": 15,
        "discovered_by": "a careful search",
        **overrides,
    }
    return Secret(**fields)


def _fixture_check(**overrides) -> FixtureCheck:
    fields = {
        "action": "pry the chest",
        "ability": "strength",
        "dc": 12,
        "success": "the lid gives way",
        **overrides,
    }
    return FixtureCheck(**fields)


def test_authored_check_reads_ability_skill_and_dc_off_a_secret():
    secret = _secret(ability="intelligence", skill="Arcana", dc=18)
    assert service.authored_check(secret) == ("intelligence", "Arcana", 18)


def test_authored_check_reads_ability_skill_and_dc_off_a_fixture_check():
    check = _fixture_check(ability="dexterity", skill="Sleight of Hand", dc=14)
    assert service.authored_check(check) == ("dexterity", "Sleight of Hand", 14)


def test_authored_check_never_reads_the_secrets_own_prose():
    secret = _secret(ability="wisdom", fact="a hidden lever behind the tapestry")
    ability, skill, dc = service.authored_check(secret)
    assert ability == "wisdom"
    assert skill is None
    assert "lever" not in (str(dc) + str(skill))


def test_an_active_check_requests_formula_uses_the_authored_ability():
    # AC3: an ability_check built from an authored fixture check derives
    # its formula off the ability the content names, not a default.
    check = _fixture_check(ability="intelligence", dc=16)
    ability, _skill, _dc = service.authored_check(check)
    actor = _character()

    formula = dice.derive_formula(
        "ability_check",
        actor,
        {"ability": ability},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    expected_modifier = dice.ability_modifier(_ABILITIES["intelligence"])
    assert formula == f"1d20{expected_modifier:+d}"


def test_a_saving_throw_formula_uses_the_authored_ability():
    secret = _secret(ability="dexterity", dc=13)
    ability, _skill, _dc = service.authored_check(secret)
    actor = _character()

    formula = dice.derive_formula(
        "saving_throw",
        actor,
        {"ability": ability},
        campaign_id=CAMPAIGN_ID,
        version=VERSION,
    )

    expected_modifier = dice.ability_modifier(_ABILITIES["dexterity"])
    assert formula == f"1d20{expected_modifier:+d}"


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


@pytest.mark.database
def test_a_passive_check_from_an_authored_secret_records_its_skill(playthrough_db):
    async def _scenario():
        user_id = generate_id()
        await _insert_user(playthrough_db, user_id, username="passive-skill")
        await playthrough_db.commit()
        run = await service.start_campaign_run(
            playthrough_db, user_id=user_id, campaign_id=CAMPAIGN_ID
        )
        character = await service.create_character(playthrough_db, user_id=user_id, run_id=run.id)

        wisdom = content_service.load_campaign(
            CAMPAIGN_ID, VERSION
        ).campaign.seed_character.abilities.wisdom
        passive_score = 10 + (wisdom - 10) // 2

        secret = _secret(ability="wisdom", skill="Perception", dc=passive_score)
        ability, skill, dc = service.authored_check(secret)

        passed = await service.passive_check(
            playthrough_db,
            user_id=user_id,
            actor_id=character.id,
            ability=ability,
            dc=dc,
            skill=skill,
        )
        assert passed is True

        row = (
            await playthrough_db.execute(
                text(
                    "SELECT payload FROM events WHERE campaign_run_id = :run_id "
                    "AND type = 'tool_call' ORDER BY id DESC LIMIT 1"
                ),
                {"run_id": run.id},
            )
        ).one()
        assert row.payload["args"]["skill"] == "Perception"

    asyncio.run(_scenario())
