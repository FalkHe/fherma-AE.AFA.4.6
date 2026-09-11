"""Tests for `app content validate` -- phase contract §7, step-1.1.md §5.4.

Criterion numbers refer to `step-1.1.md` §6 ("The CLI", 42-50).

Which Typer app drives which assertion is contract (phase contract §8):
criteria 42-48 run against `content_app` directly (no callback, so
`configure_logging()` never runs on that path); criterion 49 must run
against `cli` from `app.cli`, the only path on which the callback
configures logging.
"""

import json

from app.modules.content.commands import content_app
from typer.testing import CliRunner

from app.cli import cli
from tests.content.conftest import build_version_dir, campaign

runner = CliRunner()


def test_valid_tree_exits_0_stdout_ok_stderr_empty_c42(content_root):
    build_version_dir(content_root)

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "hollow-reach/v1: ok"
    assert result.stderr == ""


def test_one_broken_version_exits_1_and_reports_every_error_entry_c43(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert "hollow-reach/v1: ok" not in result.stdout
    stderr_lines = result.stderr.splitlines()
    assert stderr_lines  # at least one problem line
    assert all(line.startswith("hollow-reach/v1: ") for line in stderr_lines)


def test_one_valid_and_one_broken_version_c44(content_root):
    build_version_dir(content_root, version="v1")
    build_version_dir(content_root, version="v2", campaign=campaign(id="wrong-id"))

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert "hollow-reach/v1: ok" in result.stdout
    assert any(line.startswith("hollow-reach/v2: ") for line in result.stderr.splitlines())


def test_no_campaigns_directory_c45(content_root):
    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert f"no campaigns found under {content_root}" in result.stderr


def test_empty_campaigns_directory_c45(content_root):
    (content_root / "campaigns").mkdir()

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert f"no campaigns found under {content_root}" in result.stderr


def test_nonconformant_version_directory_reported_alongside_valid_one_c46(content_root):
    build_version_dir(content_root, version="v1")
    (content_root / "campaigns" / "hollow-reach" / "v1.0").mkdir()

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert "hollow-reach/v1.0: [R3] version directory name must match ^v[0-9]+$" in result.stderr
    assert "hollow-reach/v1: ok" in result.stdout


def test_campaign_with_no_conformant_version_directory_c47(content_root):
    (content_root / "campaigns" / "hollow-reach" / "not-a-version").mkdir(parents=True)

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 1
    assert "hollow-reach: no version directory found" in result.stderr


def test_cli_reads_content_root_at_call_time_not_import_time_c48(content_root):
    build_version_dir(content_root)

    result = runner.invoke(content_app, ["validate"])

    assert result.exit_code == 0
    assert "hollow-reach/v1: ok" in result.stdout


def test_no_log_record_on_stdout_or_stderr_via_the_real_cli_callback_c49(content_root):
    build_version_dir(content_root, campaign=campaign(id="wrong-id"))

    result = runner.invoke(cli, ["content", "validate"])

    assert result.exit_code == 1
    # An unconfigured structlog PrintLogger would write to stdout; the
    # command must produce no result-data lines for a run that found no
    # valid campaign version.
    assert result.stdout == ""
    for line in result.stderr.splitlines():
        assert "timestamp" not in line.lower()
        for level in ("[info", "[error", "[debug", "[warning", "level="):
            assert level not in line.lower()


def test_help_lists_content_group_and_validate_command_c50():
    top_level = runner.invoke(cli, ["--help"])
    assert top_level.exit_code == 0
    assert "content" in top_level.stdout

    content_help = runner.invoke(cli, ["content", "--help"])
    assert content_help.exit_code == 0
    assert "validate" in content_help.stdout

    openapi_result = runner.invoke(cli, ["openapi", "export"])
    assert openapi_result.exit_code == 0
    json.loads(openapi_result.stdout)  # raises if stdout has any non-JSON content
