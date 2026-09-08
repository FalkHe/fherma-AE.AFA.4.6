"""Tests for `app/cli.py`, mirroring it at the top level of the tree.

Covers the part of criterion 32 this suite can reach without a live
container: `app openapi export` prints parseable JSON and *only* JSON to
stdout. The live-stack half of 32 (`docker compose exec -T app-web app
openapi export`, and "application log lines go to stderr" as observed from
the running container) is a mode-B check against the real stack, not
something an in-process `CliRunner` run can prove - see the QA report.
"""

import json

from typer.testing import CliRunner

from app.cli import cli

runner = CliRunner()


def test_openapi_export_prints_only_parseable_json_to_stdout():
    result = runner.invoke(cli, ["openapi", "export"])

    assert result.exit_code == 0
    document = json.loads(result.stdout)  # raises if stdout has any non-JSON content
    assert document["openapi"].startswith("3.1")
    assert "/api/v1/health" in document["paths"]
