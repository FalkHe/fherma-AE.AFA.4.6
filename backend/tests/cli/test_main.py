"""Smoke tests for the root Typer application."""

from typer.testing import CliRunner

from app import __version__
from app.cli.main import app as cli

runner = CliRunner()


def test_version_prints_the_package_version() -> None:
    """`app version` is the cheapest proof that the CLI wires up at all."""
    result = runner.invoke(cli, ["version"])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == __version__
