"""Sprint 07 WI3 -- `app checkpoint ...` CLI tests."""

from typer.testing import CliRunner

from app.cli import cli
from app.core.checkpointer import service as checkpointer_service

runner = CliRunner()


def test_checkpoint_setup_command_exists_and_prints_the_contract_line(monkeypatch):
    calls = []

    async def fake_setup():
        calls.append(True)

    monkeypatch.setattr(checkpointer_service, "setup", fake_setup)

    result = runner.invoke(cli, ["checkpoint", "setup"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "checkpoints schema ready\n"
    assert calls == [True]


def test_checkpoint_setup_exits_1_with_the_failure_on_stderr_when_the_service_raises(
    monkeypatch,
):
    async def failing_setup():
        raise RuntimeError("could not reach postgres")

    monkeypatch.setattr(checkpointer_service, "setup", failing_setup)

    result = runner.invoke(cli, ["checkpoint", "setup"])

    assert result.exit_code == 1
    assert "could not reach postgres" in result.stderr
    assert result.stdout == ""
