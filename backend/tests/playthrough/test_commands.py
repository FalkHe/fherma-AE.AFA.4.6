"""WI1 (sprint 005/05b): `app playthrough cost` (`commands.py`), registered
in `app/cli.py` as `cli.add_typer(playthrough_app, name="playthrough")`.

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/srd/test_commands.py`'s style. The only seam
faked is `playthrough_service.run_cost` (module attribute, never a name
import, so the monkeypatch takes). `_fetch_cost` also opens a session via
`app.core.db.get_sessionmaker()`, but that only builds a lazy `AsyncEngine`
-- SQLAlchemy never opens a socket until a statement actually runs -- so
leaving it real here stays engine-free exactly like `srd`'s command test.

WI4 (sprint 005/07a) adds `app playthrough roll`, the command half of AC4a.
Unlike `cost`'s tests above, `roll` is driven through the real
`playthrough_service.roll`, against the shared scratch database
(`playthrough_db`, `tests/playthrough/conftest.py`) -- so every test that
exercises it carries `@pytest.mark.database` and replaces
`dice._rng` (module attribute) with a scripted `random.Random` subclass,
never the service function itself, so the printed numbers are real,
checkable output rather than an echoed stub.
"""

import asyncio
import random as random_module
from decimal import Decimal

import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from app.cli import cli
from app.core.ids import generate_id
from app.modules.content import service as content_service
from app.modules.playthrough import dice
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.schemas import RunCost, TurnCost

runner = CliRunner()

RUN_ID = generate_id()
USER_ID = generate_id()

CAMPAIGN_ID = "greenhollow"
VERSION = "v1"


def test_cost_prints_run_total_and_each_turn_with_the_null_turn_last(monkeypatch):
    async def fake_run_cost(db, *, user_id, run_id):
        assert user_id == USER_ID
        assert run_id == RUN_ID
        return RunCost(
            total=Decimal("0.001234"),
            turns=[
                TurnCost(turn_id="a-turn-id", total=Decimal("0.000500")),
                TurnCost(turn_id=None, total=Decimal("0.000734")),
            ],
        )

    monkeypatch.setattr(playthrough_service, "run_cost", fake_run_cost)

    result = runner.invoke(cli, ["playthrough", "cost", RUN_ID, "--user", USER_ID])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout == (
        f"run: {RUN_ID}\ntotal: 0.001234\nturn a-turn-id: 0.000500\nturn -: 0.000734\n"
    )


def test_cost_on_a_foreign_or_unknown_run_exits_1_with_not_found_on_stderr(monkeypatch):
    async def failing_run_cost(db, *, user_id, run_id):
        raise CampaignRunNotFoundError(run_id)

    monkeypatch.setattr(playthrough_service, "run_cost", failing_run_cost)

    result = runner.invoke(cli, ["playthrough", "cost", RUN_ID, "--user", USER_ID])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr.strip() == f"NOT_FOUND: campaign run not found: {RUN_ID}"


def test_cost_requires_both_the_run_id_and_the_user_option():
    missing_user = runner.invoke(cli, ["playthrough", "cost", RUN_ID])
    assert missing_user.exit_code != 0

    missing_run_id = runner.invoke(cli, ["playthrough", "cost", "--user", USER_ID])
    assert missing_run_id.exit_code != 0


# --- `app playthrough roll` (WI4, sprint 005/07a) ---------------------------


class _ScriptedRandom(random_module.Random):
    """Hands back a fixed, pre-scripted sequence of face values instead of
    a real one -- the seam a command test replaces so its printed numbers
    are real, checkable output (subclasses `random.Random` so an
    `isinstance` check against `dice._rng()`'s declared return type still
    passes)."""

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


async def _make_run_and_character(session, *, username: str) -> tuple[str, str]:
    owner_id = generate_id()
    await _insert_user(session, owner_id, username=username)
    await session.commit()
    run = await playthrough_service.start_campaign_run(
        session, user_id=owner_id, campaign_id=CAMPAIGN_ID
    )
    character = await playthrough_service.create_character(session, user_id=owner_id, run_id=run.id)
    return owner_id, character.id


@pytest.mark.database
def test_roll_prints_a_derivation_read_from_the_actor_and_the_rolled_result(
    playthrough_db, monkeypatch
):
    owner_id, actor_id = asyncio.run(
        _make_run_and_character(playthrough_db, username="roll-cmd-ability")
    )
    wisdom = content_service.load_campaign(
        CAMPAIGN_ID, VERSION
    ).campaign.seed_character.abilities.wisdom
    wisdom_modifier = (wisdom - 10) // 2
    monkeypatch.setattr(dice, "_rng", lambda: _ScriptedRandom([15]))

    result = runner.invoke(
        cli,
        [
            "playthrough",
            "roll",
            "ability_check",
            "--actor",
            actor_id,
            "--user",
            owner_id,
            "--ability",
            "wisdom",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    stdout = result.stdout
    # The kind, the actor and the *derived* formula -- never a number
    # supplied on the command line -- plus the dice, modifier and total
    # the server actually rolled.
    assert "ability_check" in stdout
    assert actor_id in stdout
    assert "1d20" in stdout
    assert "15" in stdout
    assert str(wisdom_modifier) in stdout
    assert str(15 + wisdom_modifier) in stdout


@pytest.mark.database
def test_roll_custom_prints_the_given_expression_and_its_rolled_total(playthrough_db):
    owner_id, actor_id = asyncio.run(
        _make_run_and_character(playthrough_db, username="roll-cmd-custom")
    )

    # A one-sided die always shows `1`: the total (`3`) can only appear if
    # the command really rolled it, not merely echoed the expression back.
    result = runner.invoke(
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
            "1d1+2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    stdout = result.stdout
    assert "custom" in stdout
    assert actor_id in stdout
    assert "1d1+2" in stdout
    assert "3" in stdout


@pytest.mark.database
def test_roll_with_a_malformed_custom_expression_exits_1_naming_the_expression(playthrough_db):
    owner_id, actor_id = asyncio.run(
        _make_run_and_character(playthrough_db, username="roll-cmd-bad-expr")
    )

    result = runner.invoke(
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

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "VALIDATION_ERROR" in result.stderr
    assert "not-a-dice-expression" in result.stderr
