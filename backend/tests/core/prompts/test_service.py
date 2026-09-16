"""Tests for `app.core.prompts.service` — sprint 06, WI1.

Behaviours: the id grammar accepts exactly three kebab segments and nothing
else; a traversal attempt is unrepresentable — rejected as an *invalid* id,
never as *not found* (← AC4's "differently"); the numerically highest
version wins when none is requested; a missing requested version never
falls back to another one (← D5); and the two error classes fire for their
own, distinguishable cause.
"""

import pytest

from app.core.prompts import errors, service
from tests.core.prompts.conftest import write_prompt

# --- Grammar: parse_prompt_id ---------------------------------------------


def test_parse_accepts_three_kebab_segments():
    assert service.parse_prompt_id("game/system/dm") == ("game", "system", "dm")


@pytest.mark.parametrize(
    "prompt_id",
    [
        "game/system",  # two segments
        "game/system/dm/extra",  # four segments
        "game",  # one segment
        "",  # empty
    ],
)
def test_parse_rejects_wrong_segment_count(prompt_id):
    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.parse_prompt_id(prompt_id)
    assert exc_info.value.code == "PROMPT_ID_INVALID"
    assert exc_info.value.value == prompt_id


@pytest.mark.parametrize(
    "prompt_id",
    [
        "Game/system/dm",  # uppercase
        "game/-system/dm",  # leading hyphen
        "game/system-/dm",  # trailing hyphen
        "game//dm",  # empty middle segment
        "game/sys tem/dm",  # space
        "game/system_a/dm",  # underscore
    ],
)
def test_parse_rejects_malformed_segment(prompt_id):
    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.parse_prompt_id(prompt_id)
    assert exc_info.value.code == "PROMPT_ID_INVALID"


# --- Traversal is unrepresentable ------------------------------------------


@pytest.mark.parametrize(
    "prompt_id",
    [
        "../etc/passwd",
        "game/../system",
        "game/system/..",
        "/game/system/dm",
        "game/system/../../../etc",
        "game/system/dm/../../../../etc",
    ],
)
def test_traversal_attempts_are_rejected_as_invalid_not_missing(prompt_id, prompts_root):
    """A traversal attempt must fail as PROMPT_ID_INVALID, never as
    PROMPT_NOT_FOUND — proving refusal happens by whitelist before any
    `Path` is built, not by checking the filesystem afterwards."""
    with pytest.raises(errors.PromptIdInvalidError):
        service.load_prompt(prompt_id)


def test_traversal_via_dot_dot_segment_never_escapes_root(prompts_root):
    outside = prompts_root.parent / "secret.md"
    outside.write_text("should never be read")
    with pytest.raises(errors.PromptIdInvalidError):
        service.load_prompt("game/prompts/..")


# --- Version resolution: numerically highest, no fallback -----------------


def test_load_prompt_picks_highest_version_numerically(prompts_root):
    write_prompt(prompts_root, "game", "v9", "system", "dm", "old text")
    write_prompt(prompts_root, "game", "v10", "system", "dm", "new text")

    resolved = service.load_prompt("game/system/dm")

    assert resolved.version == "v10"
    assert resolved.text == "new text"


def test_list_versions_ascending_numerically(prompts_root):
    write_prompt(prompts_root, "game", "v9", "system", "dm", "x")
    write_prompt(prompts_root, "game", "v2", "system", "dm", "x")
    write_prompt(prompts_root, "game", "v10", "system", "dm", "x")

    assert service.list_versions("game") == ["v2", "v9", "v10"]


def test_list_versions_empty_when_capability_absent(prompts_root):
    assert service.list_versions("nope") == []


def test_missing_requested_version_never_falls_back(prompts_root):
    write_prompt(prompts_root, "game", "v1", "system", "dm", "only version")

    with pytest.raises(errors.PromptNotFoundError) as exc_info:
        service.load_prompt("game/system/dm", version="v2")

    assert exc_info.value.relative_path == "game/prompts/v2/system/dm.md"


def test_no_versions_at_all_is_not_found(prompts_root):
    with pytest.raises(errors.PromptNotFoundError):
        service.load_prompt("game/system/dm")


def test_missing_file_within_existing_version_is_not_found(prompts_root):
    write_prompt(prompts_root, "game", "v1", "system", "dm", "hi")

    with pytest.raises(errors.PromptNotFoundError) as exc_info:
        service.load_prompt("game/system/other")

    assert exc_info.value.relative_path == "game/prompts/v1/system/other.md"


def test_bad_version_format_is_invalid(prompts_root):
    write_prompt(prompts_root, "game", "v1", "system", "dm", "text")

    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.load_prompt("game/system/dm", version="latest")

    assert exc_info.value.code == "PROMPT_ID_INVALID"
    assert exc_info.value.value == "latest"


# --- Text is verbatim; ResolvedPrompt carries the resolved version --------


def test_text_is_verbatim_no_stripping_or_normalising(prompts_root):
    raw = "  leading and trailing space \n\n"
    write_prompt(prompts_root, "game", "v1", "system", "dm", raw)

    resolved = service.load_prompt("game/system/dm")

    assert resolved.text == raw


def test_resolved_prompt_carries_capability_kind_name_and_version(prompts_root):
    path = write_prompt(prompts_root, "game", "v1", "system", "dm", "hello")

    resolved = service.load_prompt("game/system/dm")

    assert resolved == service.ResolvedPrompt(
        prompt_id="game/system/dm",
        capability="game",
        kind="system",
        name="dm",
        version="v1",
        text="hello",
        path=path,
    )


# --- Both error classes fire for their own cause (← AC4) ------------------


def test_invalid_and_not_found_are_distinguishable(prompts_root):
    write_prompt(prompts_root, "game", "v1", "system", "dm", "hi")

    with pytest.raises(errors.PromptIdInvalidError) as invalid_info:
        service.load_prompt("Game/system/dm")
    with pytest.raises(errors.PromptNotFoundError) as not_found_info:
        service.load_prompt("game/system/missing")

    assert invalid_info.value.code == "PROMPT_ID_INVALID"
    assert not_found_info.value.code == "PROMPT_NOT_FOUND"
    assert type(invalid_info.value) is not type(not_found_info.value)
