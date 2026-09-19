"""WI1 (sprint 005/05b): `app playthrough cost` (`commands.py`), registered
in `app/cli.py` as `cli.add_typer(playthrough_app, name="playthrough")`.

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/srd/test_commands.py`'s style. The only seam
faked is `playthrough_service.run_cost` (module attribute, never a name
import, so the monkeypatch takes). `_fetch_cost` also opens a session via
`app.core.db.get_sessionmaker()`, but that only builds a lazy `AsyncEngine`
-- SQLAlchemy never opens a socket until a statement actually runs -- so
leaving it real here stays engine-free exactly like `srd`'s command test.
"""

from decimal import Decimal

from typer.testing import CliRunner

from app.cli import cli
from app.core.ids import generate_id
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.playthrough.schemas import RunCost, TurnCost

runner = CliRunner()

RUN_ID = generate_id()
USER_ID = generate_id()


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
