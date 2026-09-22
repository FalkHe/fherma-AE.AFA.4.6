"""Outcome, AC5 -- sprint 009-01 WI3.

Driven through `typer.testing.CliRunner` against the real `cli`, per
`tests/srd/test_commands.py:16-26`'s style. Nothing is monkeypatched: the
options are pure hand-authored data, so the command needs no seam."""

from typer.testing import CliRunner

from app.cli import cli

runner = CliRunner()


def test_options_command_exits_0_and_lists_the_srd_options():
    result = runner.invoke(cli, ["character", "options"])

    assert result.exit_code == 0, result.output
    assert "Barbarian" in result.stdout
    assert "d12" in result.stdout
    assert "strength, constitution" in result.stdout
    assert "greataxe" in result.stdout
