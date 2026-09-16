"""qa acceptance tests -- sprint 001/06: a prompt resolves by id at a
named version (AC1-AC5).

Black-box: every test drives `app.core.prompts.service.load_prompt()` /
`list_versions()` / `parse_prompt_id()` directly, or the real
`app prompt show` CLI command through `typer.testing.CliRunner` -- never a
private helper, never the implementation modules themselves. Every fixture
tree lives under `tmp_path`, built with the package's shared `write_prompt`
helper and `prompts_root` fixture (`tests/core/prompts/conftest.py`), which
repoints `service.PROMPT_MODULES_ROOT` there via `monkeypatch`; nothing
here depends on real repo content, since a sibling work item is landing a
seed prompt in parallel and its text may change.
"""

import httpx
import pytest
from typer.testing import CliRunner

import app.core.db as db_module
from app.cli import cli
from app.core.prompts import service
from app.core.prompts.errors import PromptError, PromptIdInvalidError, PromptNotFoundError
from app.core.settings import get_settings
from tests.core.prompts.conftest import write_prompt as _write_prompt

runner = CliRunner()


class TestAC1VerbatimText:
    """A prompt under its owning module's `prompts/` resolves and its text
    is printed byte for byte (← AC1). The sharp case is trailing whitespace
    and a blank final line -- a resolver that strips would pass a lazy
    comparison and corrupt a real prompt."""

    def test_ac1_service_text_is_the_files_exact_bytes(self, prompts_root):
        # ← AC1
        text = "You are the Dungeon Master.  \nBe vivid.\n\n"
        path = _write_prompt(prompts_root, "game", "v1", "system", "dm", text)

        resolved = service.load_prompt("game/system/dm")

        assert resolved.text == text
        assert resolved.text.encode() == path.read_bytes()

    def test_ac1_cli_stdout_is_the_files_exact_bytes_and_nothing_else(self, prompts_root):
        # ← AC1
        text = "Line one.\nLine two with trailing spaces.   \n\n"
        path = _write_prompt(prompts_root, "game", "v1", "system", "dm", text)

        result = runner.invoke(cli, ["prompt", "show", "game/system/dm"])

        assert result.exit_code == 0
        assert result.stdout == text
        assert result.stdout.encode() == path.read_bytes()


class TestAC2VersionResolution:
    """`--version v1` prints that version; with no flag the numerically
    highest resolves (← AC2). `v9`/`v10` is the sharp case a lexical sort
    gets wrong. Requesting a version that does not exist must fail, never
    silently fall back to another (D5)."""

    def test_ac2_default_resolves_numerically_highest_not_lexically(self, prompts_root):
        # ← AC2: lexical sort would wrongly pick "v9" over "v10".
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "v1 text\n")
        _write_prompt(prompts_root, "game", "v9", "system", "dm", "v9 text\n")
        path_v10 = _write_prompt(prompts_root, "game", "v10", "system", "dm", "v10 text\n")

        resolved = service.load_prompt("game/system/dm")

        assert resolved.version == "v10"
        assert resolved.text == "v10 text\n"
        assert resolved.path == path_v10

    def test_ac2_explicit_version_flag_resolves_exactly_that_version(self, prompts_root):
        # ← AC2
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "v1 text\n")
        _write_prompt(prompts_root, "game", "v2", "system", "dm", "v2 text\n")

        resolved = service.load_prompt("game/system/dm", version="v1")

        assert resolved.version == "v1"
        assert resolved.text == "v1 text\n"

    def test_ac2_nonexistent_version_fails_rather_than_falling_back(self, prompts_root):
        # ← AC2: D5 forbids a silent fallback that would change which
        # prompt a playthrough started with.
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "v1 text\n")

        with pytest.raises(PromptNotFoundError):
            service.load_prompt("game/system/dm", version="v2")

    def test_ac2_list_versions_sorts_numerically_not_lexically(self, prompts_root):
        # ← AC2: `list_versions` is the interface a caller uses to see
        # which version counts as "highest".
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "one\n")
        _write_prompt(prompts_root, "game", "v9", "system", "dm", "nine\n")
        _write_prompt(prompts_root, "game", "v10", "system", "dm", "ten\n")

        versions = service.list_versions("game")

        assert versions[-1] == "v10"
        assert versions == sorted(versions, key=lambda v: int(v[1:]))

    def test_ac2_cli_default_and_pinned_version_agree_with_the_service(self, prompts_root):
        # ← AC2: the same v9/v10 sharp case through the real CLI.
        _write_prompt(prompts_root, "game", "v9", "system", "dm", "nine\n")
        _write_prompt(prompts_root, "game", "v10", "system", "dm", "ten\n")

        default_result = runner.invoke(cli, ["prompt", "show", "game/system/dm"])
        pinned_result = runner.invoke(cli, ["prompt", "show", "game/system/dm", "--version", "v9"])

        assert default_result.exit_code == 0
        assert default_result.stdout == "ten\n"
        assert pinned_result.exit_code == 0
        assert pinned_result.stdout == "nine\n"

    def test_ac2_cli_nonexistent_version_fails_rather_than_falling_back(self, prompts_root):
        # ← AC2
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "v1 text\n")

        result = runner.invoke(cli, ["prompt", "show", "game/system/dm", "--version", "v2"])

        assert result.exit_code != 0
        assert result.stdout == ""


class TestAC3ResolvedVersionReachesTheTerminal:
    """The resolved version identifier is printed alongside the text, so a
    run could record which version it started with (← AC3, D5)."""

    def test_ac3_service_result_carries_prompt_id_and_resolved_version(self, prompts_root):
        # ← AC3
        _write_prompt(prompts_root, "game", "v3", "system", "dm", "text\n")

        resolved = service.load_prompt("game/system/dm")

        assert resolved.version == "v3"
        assert resolved.prompt_id == "game/system/dm"
        assert resolved.capability == "game"
        assert resolved.kind == "system"
        assert resolved.name == "dm"

    def test_ac3_cli_stderr_reports_resolved_prompt_id_and_version(self, prompts_root):
        # ← AC3: text on stdout, the resolved version identifier on stderr
        # -- both reach the terminal from one run.
        _write_prompt(prompts_root, "game", "v2", "system", "dm", "text\n")

        result = runner.invoke(cli, ["prompt", "show", "game/system/dm"])

        assert result.exit_code == 0
        assert "resolved: game/system/dm v2" in result.stderr
        assert result.stdout == "text\n"


class TestAC4InvalidVsNotFoundFailDifferently:
    """An unknown id and a malformed id fail differently: different codes,
    different exit statuses, both non-zero (← AC4). Traversal attempts are
    rejected by the grammar as *invalid*, never surfacing as *not found*."""

    def test_ac4_parse_prompt_id_splits_a_valid_id_into_its_three_parts(self):
        # ← AC4
        capability, kind, name = service.parse_prompt_id("game/system/dm")

        assert (capability, kind, name) == ("game", "system", "dm")

    def test_ac4_unknown_id_raises_not_found_with_its_own_code(self, prompts_root):
        # ← AC4
        with pytest.raises(PromptNotFoundError) as excinfo:
            service.load_prompt("game/system/does-not-exist")

        assert excinfo.value.code == "PROMPT_NOT_FOUND"

    @pytest.mark.parametrize(
        "malformed_id",
        [
            "game/system",  # too few segments
            "game/system/dm/extra",  # too many segments
            "Game/system/dm",  # uppercase
            "game/system/-dm",  # leading hyphen
            "game/system/dm-",  # trailing hyphen
            "game//dm",  # empty segment
            "game/system/",  # trailing empty segment
        ],
    )
    def test_ac4_malformed_id_raises_invalid_with_its_own_code(self, prompts_root, malformed_id):
        # ← AC4
        with pytest.raises(PromptIdInvalidError) as excinfo:
            service.load_prompt(malformed_id)

        assert excinfo.value.code == "PROMPT_ID_INVALID"

    @pytest.mark.parametrize(
        "traversal_id",
        [
            "../game/system/dm",
            "game/../system/dm",
            "game/system/../dm",
            "/etc/passwd",
            "game/system/../../etc/passwd",
        ],
    )
    def test_ac4_traversal_attempt_is_rejected_as_invalid_not_not_found(
        self, prompts_root, traversal_id
    ):
        # ← AC4: the grammar refuses these outright; a test that accepted
        # "not found" here would let someone weaken the grammar later
        # unnoticed.
        with pytest.raises(PromptIdInvalidError) as excinfo:
            service.load_prompt(traversal_id)

        assert excinfo.value.code == "PROMPT_ID_INVALID"

    def test_ac4_not_found_and_invalid_are_distinct_exception_types(self, prompts_root):
        # ← AC4: both non-zero (raise), but distinguishable classes with
        # distinct codes -- neither subclasses the other.
        assert issubclass(PromptNotFoundError, PromptError)
        assert issubclass(PromptIdInvalidError, PromptError)
        assert not issubclass(PromptNotFoundError, PromptIdInvalidError)
        assert not issubclass(PromptIdInvalidError, PromptNotFoundError)

        with pytest.raises(PromptNotFoundError):
            service.load_prompt("game/system/missing")
        with pytest.raises(PromptIdInvalidError):
            service.load_prompt("not valid")

    def test_ac4_cli_not_found_exits_3_and_reports_its_code(self, prompts_root):
        # ← AC4
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "text\n")

        result = runner.invoke(cli, ["prompt", "show", "game/system/does-not-exist"])

        assert result.exit_code == 3
        assert "PROMPT_NOT_FOUND" in result.stderr
        assert result.stdout == ""

    def test_ac4_cli_invalid_id_exits_2_and_reports_its_code(self, prompts_root):
        # ← AC4
        result = runner.invoke(cli, ["prompt", "show", "Game/System/DM"])

        assert result.exit_code == 2
        assert "PROMPT_ID_INVALID" in result.stderr
        assert result.stdout == ""

    def test_ac4_cli_malformed_version_flag_exits_2_as_invalid(self, prompts_root):
        # ← AC4: a malformed `--version` is an invalid-shaped failure, not
        # a not-found.
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "text\n")

        result = runner.invoke(
            cli, ["prompt", "show", "game/system/dm", "--version", "version-one"]
        )

        assert result.exit_code == 2
        assert "PROMPT_ID_INVALID" in result.stderr
        assert result.stdout == ""

    def test_ac4_cli_traversal_attempt_exits_2_as_invalid_not_3_as_not_found(self, prompts_root):
        # ← AC4
        result = runner.invoke(cli, ["prompt", "show", "../game/system/dm"])

        assert result.exit_code == 2
        assert "PROMPT_ID_INVALID" in result.stderr
        assert result.stdout == ""

    def test_ac4_cli_exit_codes_for_not_found_and_invalid_differ(self, prompts_root):
        # ← AC4: different codes, different exit statuses, both non-zero.
        not_found = runner.invoke(cli, ["prompt", "show", "game/system/does-not-exist"])
        invalid = runner.invoke(cli, ["prompt", "show", "not valid"])

        assert not_found.exit_code != 0
        assert invalid.exit_code != 0
        assert not_found.exit_code != invalid.exit_code


class TestAC5NoProviderNoDatabase:
    """The whole thing runs without an API key and without a database --
    this sprint is purely the filesystem (← AC5). Asserted, not assumed:
    a blank API key, a real DB engine poisoned to fail if constructed, and
    a real network transport poisoned to fail if reached."""

    def _poison_provider_and_db(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        get_settings.cache_clear()

        def _forbidden_transport(*args, **kwargs):
            raise AssertionError("a real network call was attempted")

        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _forbidden_transport)

        def _forbidden_engine():
            raise AssertionError("a real DB engine was constructed")

        monkeypatch.setattr(db_module, "get_engine", _forbidden_engine)

    def test_ac5_service_resolves_with_no_api_key_no_db_engine_and_no_network(
        self, prompts_root, monkeypatch
    ):
        # ← AC5
        self._poison_provider_and_db(monkeypatch)
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "text\n")

        try:
            resolved = service.load_prompt("game/system/dm")
        finally:
            get_settings.cache_clear()

        assert resolved.text == "text\n"

    def test_ac5_cli_runs_with_no_api_key_no_db_engine_and_no_network(
        self, prompts_root, monkeypatch
    ):
        # ← AC5
        self._poison_provider_and_db(monkeypatch)
        _write_prompt(prompts_root, "game", "v1", "system", "dm", "text\n")

        try:
            result = runner.invoke(cli, ["prompt", "show", "game/system/dm"])
        finally:
            get_settings.cache_clear()

        assert result.exit_code == 0
        assert result.stdout == "text\n"
