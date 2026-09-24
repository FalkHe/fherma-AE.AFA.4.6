"""qa acceptance tests -- sprint 005/07a "a roll is derived by the server
and recorded as it fell"
(`docs/intents/005-game-state-services/sprints/07a-rolls-derived-and-recorded/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.dice`,
`.service` or `.commands` themselves -- those are this sprint's own work
items, written in parallel, and this file never reads them.

AC1 needs no database (`plan.md`: "unit tests, `_rng` monkeypatched"):
`dice.roll(expression)` and `derive_formula(kind, actor, context, *,
campaign_id, version)` are exercised against a duck-typed actor (the same
shape `objects` rows carry -- `template_id`, `state`) and the real, shipped
`greenhollow/v1` content, read through `app.modules.content.service` so
this file survives an authored-content change rather than pasting its
numbers as literals. `dice._rng` is monkeypatched, scoped to
`pytest.MonkeyPatch.context()` per call, to a small `random.Random`
subclass that hands back a scripted, exhausted-in-order sequence of face
values -- "replace the random source so results are fixed", per the
brief -- never asserting that `_rng` was merely called.

Because `derive_formula`'s home module is not fixed by the interface
contract (only its signature is), it is looked up dynamically on whichever
of `dice` / `service` actually defines it.

AC2 and the database half of AC4a carry `@pytest.mark.database`: they
drive `start_campaign_run` / `create_character` / the new producers
directly against the shared scratch-database fixture (`playthrough_db`,
`tests/playthrough/conftest.py`) and read the result back with plain SQL
over `events`, never the ORM model classes for anything this sprint
writes -- same pattern as `test_acceptance_transcript_writer_and_read.py`.
AC4a's CLI half drives the real `app playthrough roll` command through
`CliRunner` against the same scratch database (`DATABASE_URL` is already
pinned for the duration by `playthrough_db`); its `custom` expression is
chosen as `1d1+5` on purpose -- a one-sided die always rolls a `1`, so the
printed total (`6`) is fully deterministic without touching `_rng` at all,
proving the command really rolled rather than merely echoing its input.

AC5 needs no database either: `content.schemas.FixtureCheck` / `Secret`
are instantiated directly, and the shipped `greenhollow/v1` campaign is
loaded through `content.service.load_campaign` -- no mocks, the real
authored tree.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas): every async call
in one test is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the
implementation itself -- this suite is red until the corresponding work
items land, and green once they do.
"""

import asyncio
import inspect
import random as random_module
import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.content import schemas as content_schemas
from app.modules.content import service as content_service
from app.modules.playthrough import service as playthrough_service

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"

runner = CliRunner()


class _ScriptedRandom(random_module.Random):
    """A `random.Random` subclass whose `randint` hands back a fixed,
    pre-scripted sequence of face values, one per call, instead of a real
    one -- the seam the brief asks for ("replace the random source so
    results are fixed and you can assert real numbers"). Subclassing
    `random.Random` (rather than a bare duck type) means an `isinstance`
    check the implementation might make against `dice._rng()`'s declared
    return type still passes."""

    def __init__(self, faces: list[int]) -> None:
        super().__init__()
        self._faces = list(faces)

    def randint(self, a: int, b: int) -> int:  # noqa: ARG002 - scripted, bounds ignored
        return self._faces.pop(0)


def _dice_module():
    from app.modules.playthrough import dice

    return dice


def _resolve_derive_formula():
    """`derive_formula`'s home module is not fixed by the interface
    contract (only `derive_formula(kind, actor, context, *, campaign_id,
    version) -> str` is) -- `plan.md`'s work-item split puts it alongside
    the producers in `service.py`, but nothing stops it living in
    `dice.py` next to the parser it was introduced beside in the brief's
    own sentence. Looked up on whichever module actually defines it."""
    dice = _dice_module()
    found = getattr(dice, "derive_formula", None) or getattr(
        playthrough_service, "derive_formula", None
    )
    assert found is not None, "derive_formula not found on dice or service"
    return found


def _rolled_with(monkeypatch, dice, formula: str, faces: list[int]):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(dice, "_rng", lambda: _ScriptedRandom(faces))
        return dice.roll(formula)


def _make_actor(abilities: dict) -> SimpleNamespace:
    """A duck-typed stand-in for a template-less `objects` row (a
    character): `template_id=None`, abilities in `state["abilities"]`,
    exactly the shape `create_character` writes
    (`test_acceptance_character_and_shelf_life.py`)."""
    return SimpleNamespace(
        id=generate_id(),
        kind="creature",
        template_id=None,
        state={"abilities": abilities},
    )


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _event_rows(session, run_id: str, *, type_: str | None = None):
    query = "SELECT id, type, visibility, payload FROM events WHERE campaign_run_id = :run_id"
    params = {"run_id": run_id}
    if type_ is not None:
        query += " AND type = :type"
        params["type"] = type_
    query += " ORDER BY id"
    return (await session.execute(text(query), params)).all()


def test_ac1_a_roll_is_derived_from_kind_and_actor_alone(monkeypatch):
    # <- AC1
    dice = _dice_module()
    derive_formula = _resolve_derive_formula()

    # -- `dice.roll` parses `NdM+K`/`NdM-K` and rolls behind the `_rng()`
    # seam: fixed faces in, real, checkable numbers out.
    plus = _rolled_with(monkeypatch, dice, "2d6+3", [4, 5])
    assert plus.faces == [4, 5]
    assert plus.modifier == 3
    assert plus.total == 12

    minus = _rolled_with(monkeypatch, dice, "1d20-1", [10])
    assert minus.faces == [10]
    assert minus.modifier == -1
    assert minus.total == 9

    # -- A malformed expression is refused, naming the expression itself,
    # with the shared validation domain code.
    with pytest.raises(Exception) as bad_expr:
        dice.roll("not-a-dice-expression")
    assert bad_expr.value.code == ErrorCode.VALIDATION_ERROR
    assert "not-a-dice-expression" in str(bad_expr.value)

    # -- Derivation: an actor's abilities, read from nowhere but the actor
    # itself.
    abilities = {
        "strength": 10,
        "dexterity": 14,
        "constitution": 12,
        "intelligence": 10,
        "wisdom": 13,
        "charisma": 8,
    }
    actor = _make_actor(abilities)
    wisdom_modifier = (abilities["wisdom"] - 10) // 2  # 1, the SRD formula
    dexterity_modifier = (abilities["dexterity"] - 10) // 2  # 2

    # An ability check uses that ability's modifier -- and nothing else:
    # the caller supplies no number, only which ability.
    check_formula = derive_formula(
        "ability_check", actor, {"ability": "wisdom"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    check_roll = _rolled_with(monkeypatch, dice, check_formula, [15])
    assert check_roll.modifier == wisdom_modifier
    assert check_roll.total == check_roll.faces[0] + wisdom_modifier

    # A saving throw, same rule, a different ability.
    save_formula = derive_formula(
        "saving_throw", actor, {"ability": "dexterity"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    save_roll = _rolled_with(monkeypatch, dice, save_formula, [7])
    assert save_roll.modifier == dexterity_modifier
    assert save_roll.total == save_roll.faces[0] + dexterity_modifier

    # Initiative always uses Dexterity -- even when the context asks for a
    # different ability, proving the kind decides, not the caller.
    initiative_formula = derive_formula(
        "initiative", actor, {"ability": "wisdom"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    initiative_roll = _rolled_with(monkeypatch, dice, initiative_formula, [3])
    assert initiative_roll.modifier == dexterity_modifier

    # An attack uses the named weapon's to-hit -- read from the real,
    # shipped item template, never pasted as a literal.
    knife = content_service.load_object_template(CAMPAIGN_ID, VERSION, "shepherds-knife")
    assert len(knife.attacks) == 1  # unambiguous: no attack name is needed
    attack_formula = derive_formula(
        "attack", actor, {"item_id": "shepherds-knife"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    attack_roll = _rolled_with(monkeypatch, dice, attack_formula, [11])
    assert attack_roll.modifier == knife.attacks[0].to_hit

    # Damage uses the same weapon's damage expression, verbatim.
    damage_formula = derive_formula(
        "damage", actor, {"item_id": "shepherds-knife"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    assert damage_formula == knife.attacks[0].damage

    # A custom roll uses the expression it was given, verbatim, and
    # nothing else.
    custom_formula = derive_formula(
        "custom", actor, {"expression": "3d6+1"}, campaign_id=CAMPAIGN_ID, version=VERSION
    )
    assert custom_formula == "3d6+1"


@pytest.mark.database
def test_ac2_a_request_its_answer_an_outright_roll_and_a_passive_check_are_recorded(
    playthrough_db,
):
    # <- AC2
    # -- Structural (← I4, the decision the sprint rests on): no producer
    # takes a number -- there is no parameter named `formula`, `modifier`,
    # `bonus`, `faces` or `total` anywhere on any of them.
    forbidden_names = {"formula", "modifier", "bonus", "faces", "total"}
    for fn in (
        playthrough_service.request_player_roll,
        playthrough_service.resolve_roll_request,
        playthrough_service.roll,
        playthrough_service.passive_check,
        playthrough_service.ask_player,
    ):
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden_names), (fn.__name__, params & forbidden_names)

    async def _scenario():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac2-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        sheet = content_service.load_campaign(CAMPAIGN_ID, VERSION).campaign.seed_character
        wisdom_modifier = (sheet.abilities.wisdom - 10) // 2

        # -- Asking the player to roll records the request: kind, actor,
        # formula -- and nothing resembling a rolled result yet.
        requested = await playthrough_service.request_player_roll(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="ability_check",
            context={"ability": "wisdom"},
        )
        assert requested.type == "roll_requested"
        request_row = (
            await playthrough_db.execute(
                text("SELECT type, visibility, payload FROM events WHERE id = :id"),
                {"id": requested.id},
            )
        ).one()
        assert request_row.type == "roll_requested"
        requested_payload = request_row.payload
        assert requested_payload["kind"] == "ability_check"
        assert requested_payload["actorId"] == str(character.id)
        assert "faces" not in requested_payload
        assert "total" not in requested_payload

        # -- Answering that request records the roll: dice, modifier,
        # total -- at the same visibility the request had.
        answered = await playthrough_service.resolve_roll_request(
            playthrough_db, user_id=owner_id, request_id=requested.id
        )
        assert answered.type == "roll"
        answer_row = (
            await playthrough_db.execute(
                text("SELECT type, visibility, payload FROM events WHERE id = :id"),
                {"id": answered.id},
            )
        ).one()
        assert answer_row.type == "roll"
        assert answer_row.visibility == request_row.visibility
        answer_payload = answer_row.payload
        assert answer_payload["requestId"] == str(requested.id)
        assert answer_payload["kind"] == "ability_check"
        assert answer_payload["modifier"] == wisdom_modifier
        assert isinstance(answer_payload["faces"], list) and len(answer_payload["faces"]) >= 1
        assert answer_payload["total"] == sum(answer_payload["faces"]) + wisdom_modifier

        # -- Rolling outright does both at once, at the visibility given
        # (default here, exercised as the hidden path -- a roll nobody was
        # asked to make).
        rolled = await playthrough_service.roll(
            playthrough_db,
            user_id=owner_id,
            actor_id=character.id,
            kind="initiative",
            context={},
        )
        assert rolled.type == "roll"
        outright_rows = await _event_rows(playthrough_db, run.id, type_="roll_requested")
        outright_requests = [r for r in outright_rows if r.payload.get("kind") == "initiative"]
        assert len(outright_requests) == 1
        outright_roll_row = (
            await playthrough_db.execute(
                text("SELECT payload, visibility FROM events WHERE id = :id"), {"id": rolled.id}
            )
        ).one()
        assert outright_roll_row.payload["requestId"] == str(outright_requests[0].id)
        # Both halves share one visibility -- and it is not the player's,
        # since nobody was asked.
        assert outright_requests[0].visibility == outright_roll_row.visibility == "dm"

        # -- A passive check -- nobody asked for it -- is recorded for the
        # DM only, and has no dice in it at all.
        events_before = len(await _event_rows(playthrough_db, run.id))
        passed = await playthrough_service.passive_check(
            playthrough_db, user_id=owner_id, actor_id=character.id, ability="wisdom", dc=10
        )
        assert passed == (10 + wisdom_modifier >= 10)
        all_rows = await _event_rows(playthrough_db, run.id)
        assert len(all_rows) == events_before + 1
        passive_row = all_rows[-1]
        assert passive_row.type == "tool_call"
        assert passive_row.visibility == "dm"
        assert "faces" not in passive_row.payload

    asyncio.run(_scenario())


@pytest.mark.database
def test_ac4a_a_question_is_recorded_and_the_command_prints_the_working(playthrough_db):
    # <- AC4a
    async def _setup():
        owner_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac4a-owner")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id=CAMPAIGN_ID
        )
        character = await playthrough_service.create_character(
            playthrough_db, user_id=owner_id, run_id=run.id
        )

        # -- Asking the player a question is recorded as a `question`.
        await playthrough_service.ask_player(
            playthrough_db,
            user_id=owner_id,
            run_id=run.id,
            text="Which door do you take?",
            options=["left", "right"],
        )
        question_rows = await _event_rows(playthrough_db, run.id, type_="question")
        assert len(question_rows) == 1
        assert question_rows[0].payload["text"] == "Which door do you take?"
        assert question_rows[0].payload["options"] == ["left", "right"]
        assert question_rows[0].visibility == "player"

        return owner_id, character.id

    owner_id, actor_id = asyncio.run(_setup())

    # -- The command prints the working: kind, actor, formula, dice,
    # modifier and total. A `custom` roll of `1d1+5` is deterministic
    # without touching the RNG seam at all: a one-sided die can only ever
    # show `1`, so the total (`6`) can only appear if the command really
    # derived and rolled it, not merely echoed its input.
    success = runner.invoke(
        cli,
        [
            "playthrough",
            "roll",
            "custom",
            "--actor",
            actor_id,
            "--user",
            owner_id,
            "--expression",
            "1d1+5",
        ],
    )
    assert success.exit_code == 0, success.output
    assert success.stderr == ""
    stdout = success.stdout
    assert re.search(r"\bcustom\b", stdout)
    assert actor_id in stdout
    assert "1d1+5" in stdout
    assert re.search(r"\b5\b", stdout)  # the modifier
    assert re.search(r"\b6\b", stdout)  # the total: the die can only show 1

    # -- A bad `custom` expression makes the command fail, naming the
    # expression, same failure shape as `app playthrough cost`.
    failure = runner.invoke(
        cli,
        [
            "playthrough",
            "roll",
            "custom",
            "--actor",
            actor_id,
            "--user",
            owner_id,
            "--expression",
            "not-a-dice-expression",
        ],
    )
    assert failure.exit_code == 1
    assert failure.stdout == ""
    assert "not-a-dice-expression" in failure.stderr


def test_ac5_the_authored_difficulty_floor_matches_the_srd_table():
    # <- AC5
    # A difficulty below 5 is refused for both authored shapes that carry
    # one.
    with pytest.raises(ValidationError):
        content_schemas.FixtureCheck(
            action="pick the lock", ability="wisdom", dc=4, success="It opens."
        )
    with pytest.raises(ValidationError):
        content_schemas.Secret(
            fact="A hidden latch", ability="wisdom", dc=4, discovered_by="a search"
        )

    # One at 5 (the SRD's own floor) or above is accepted.
    check = content_schemas.FixtureCheck(
        action="pick the lock", ability="wisdom", dc=5, success="It opens."
    )
    assert check.dc == 5
    secret = content_schemas.Secret(
        fact="A hidden latch", ability="wisdom", dc=5, discovered_by="a search"
    )
    assert secret.dc == 5

    # Nothing shipped breaks: the real, authored Greenhollow campaign and
    # its adventure still validate end-to-end against the raised floor.
    loaded = content_service.load_campaign(CAMPAIGN_ID, VERSION)
    assert loaded is not None
