"""Tests for `app prompt show` -- sprint 06 WI2, brief AC1-AC4
(`docs/intents/001-llm-access-scaffolding/sprints/06-prompt-assets/brief.md`).

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/content/test_cli.py`'s and `tests/core/llm/
test_commands.py`'s style: split `result.stdout` / `result.stderr`. The only
seam faked is the resolver's root -- `prompt_service.PROMPT_MODULES_ROOT`
is repointed at a fixture tree built under `tmp_path`, never against real
repo content (a sibling work item is landing a seed file in parallel).

No conftest here (out of this work item's file list): each test builds its
own small `<root>/<capability>/prompts/<version>/<kind>/<id>.md` tree.
"""

from pathlib import Path

from typer.testing import CliRunner

from app.cli import cli
from app.core.prompts import service as prompt_service

runner = CliRunner()


def _write_prompt(
    root: Path, capability: str, version: str, kind: str, name: str, text: str
) -> Path:
    path = root / capability / "prompts" / version / kind / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_ac1_resolves_by_id_and_prints_the_text_verbatim(tmp_path, monkeypatch):
    # ← AC1
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    text = "You are the dungeon master.\nStay in character.\n"
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", text)

    result = runner.invoke(cli, ["prompt", "show", "game/system/smoke", "--version", "v1"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == text


def test_ac2_explicit_version_flag_selects_that_version(tmp_path, monkeypatch):
    # ← AC2
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "version one text")
    _write_prompt(tmp_path, "game", "v2", "system", "smoke", "version two text")

    result = runner.invoke(cli, ["prompt", "show", "game/system/smoke", "--version", "v1"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "version one text"


def test_ac2_no_version_flag_resolves_the_highest_version(tmp_path, monkeypatch):
    # ← AC2
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "version one text")
    _write_prompt(tmp_path, "game", "v2", "system", "smoke", "version two text")

    result = runner.invoke(cli, ["prompt", "show", "game/system/smoke"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout == "version two text"


def test_ac3_stderr_reports_the_resolved_prompt_id_and_version(tmp_path, monkeypatch):
    # ← AC3
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v3", "system", "smoke", "the text")

    result = runner.invoke(cli, ["prompt", "show", "game/system/smoke"])

    assert result.exit_code == 0, result.stderr
    assert result.stderr.strip() == "resolved: game/system/smoke v3"
    # Stdout stays exactly the file's text -- the resolved line never
    # leaks onto the pipeable stream.
    assert result.stdout == "the text"


def test_ac4_unknown_id_fails_not_found_with_its_own_code_and_exit_3(tmp_path, monkeypatch):
    # ← AC4
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "the text")

    result = runner.invoke(cli, ["prompt", "show", "game/system/missing"])

    assert result.exit_code == 3
    assert "PROMPT_NOT_FOUND" in result.stderr
    assert result.stdout == ""


def test_ac4_malformed_id_fails_invalid_with_its_own_code_and_exit_2(tmp_path, monkeypatch):
    # ← AC4
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "the text")

    result = runner.invoke(cli, ["prompt", "show", "Game/System/Smoke"])

    assert result.exit_code == 2
    assert "PROMPT_ID_INVALID" in result.stderr
    assert result.stdout == ""


def test_ac4_not_found_and_invalid_fail_with_different_exit_codes(tmp_path, monkeypatch):
    # ← AC4 -- the two failure paths must not collapse into one exit code.
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "the text")

    not_found = runner.invoke(cli, ["prompt", "show", "game/system/missing"])
    invalid = runner.invoke(cli, ["prompt", "show", "not-three-segments"])

    assert not_found.exit_code == 3
    assert invalid.exit_code == 2
    assert not_found.exit_code != invalid.exit_code


def test_ac4_malformed_version_flag_fails_invalid_with_exit_2(tmp_path, monkeypatch):
    # ← AC4 -- a bad `--version` is invalid, not not-found.
    monkeypatch.setattr(prompt_service, "PROMPT_MODULES_ROOT", tmp_path)
    _write_prompt(tmp_path, "game", "v1", "system", "smoke", "the text")

    result = runner.invoke(cli, ["prompt", "show", "game/system/smoke", "--version", "one"])

    assert result.exit_code == 2
    assert "PROMPT_ID_INVALID" in result.stderr
