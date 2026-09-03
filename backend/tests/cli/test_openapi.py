"""Tests for `app openapi export`.

The command must work with PostgreSQL down, so nothing here provides a
database: building the app and rendering its schema opens no connection.
"""

import json
from pathlib import Path

from typer.testing import CliRunner

from app.cli.main import app as cli

runner = CliRunner()


def test_export_writes_the_schema_to_the_requested_file(tmp_path: Path) -> None:
    """The file holds parsable JSON describing the documented routes."""
    target = tmp_path / "openapi.json"

    result = runner.invoke(cli, ["openapi", "export", "--out", str(target)])

    assert result.exit_code == 0, result.output
    schema = json.loads(target.read_text(encoding="utf-8"))
    assert schema["openapi"].startswith("3.")
    # A subset check, so mounting a further router does not fail this test.
    assert {"/health", "/ready"} <= set(schema["paths"])


def test_export_fails_with_a_message_when_the_target_is_unwritable(tmp_path: Path) -> None:
    """An unwritable path exits non-zero and explains itself, without a traceback."""
    target = tmp_path / "missing-directory" / "openapi.json"

    result = runner.invoke(cli, ["openapi", "export", "--out", str(target)])

    assert result.exit_code == 1
    assert "Could not write" in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert not target.exists()
