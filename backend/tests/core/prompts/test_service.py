"""Tests for `app.core.prompts.service` — sprint 06, WI1.

Behaviours: the id grammar accepts exactly three kebab segments and nothing
else; a traversal attempt is unrepresentable — rejected as an *invalid* id,
never as *not found* (← AC4's "differently"); the numerically highest
version wins when none is requested; a missing requested version never
falls back to another one (← D5); and the two error classes fire for their
own, distinguishable cause.

Round-2: a trailing newline must not slip through `$`-anchored grammar
(Python's `$` matches before a trailing `\n`) — proven both for the id and
for `--version`, and proven with no filesystem access at all, not merely
with the right exception type. Prompt text is read as raw bytes, so a CRLF
file round-trips byte for byte instead of being silently normalised by
`Path.read_text()`'s universal-newline translation. `list_versions` closes
the same traversal hole `load_prompt` already closes for `capability`.
"""

from pathlib import Path

import pytest

from app.core.prompts import errors, service
from tests.core.prompts.conftest import write_prompt

# --- Grammar: parse_prompt_id ---------------------------------------------


def test_parse_accepts_three_kebab_segments():
    assert service.parse_prompt_id("sample/system/story") == ("sample", "system", "story")


@pytest.mark.parametrize(
    "prompt_id",
    [
        "sample/system",  # two segments
        "sample/system/story/extra",  # four segments
        "sample",  # one segment
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
        "Sample/system/story",  # uppercase
        "game/-system/dm",  # leading hyphen
        "sample/system-/dm",  # trailing hyphen
        "game//dm",  # empty middle segment
        "game/sys tem/dm",  # space
        "sample/system_a/dm",  # underscore
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
        "sample/system/..",
        "/sample/system/story",
        "sample/system/../../../etc",
        "sample/system/story/../../../../etc",
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
        service.load_prompt("sample/prompts/..")


# --- Version resolution: numerically highest, no fallback -----------------


def test_load_prompt_picks_highest_version_numerically(prompts_root):
    write_prompt(prompts_root, "sample", "v9", "system", "story", "old text")
    write_prompt(prompts_root, "sample", "v10", "system", "story", "new text")

    resolved = service.load_prompt("sample/system/story")

    assert resolved.version == "v10"
    assert resolved.text == "new text"


def test_list_versions_ascending_numerically(prompts_root):
    write_prompt(prompts_root, "sample", "v9", "system", "story", "x")
    write_prompt(prompts_root, "sample", "v2", "system", "story", "x")
    write_prompt(prompts_root, "sample", "v10", "system", "story", "x")

    assert service.list_versions("sample") == ["v2", "v9", "v10"]


def test_list_versions_empty_when_capability_absent(prompts_root):
    assert service.list_versions("nope") == []


def test_missing_requested_version_never_falls_back(prompts_root):
    write_prompt(prompts_root, "sample", "v1", "system", "story", "only version")

    with pytest.raises(errors.PromptNotFoundError) as exc_info:
        service.load_prompt("sample/system/story", version="v2")

    assert exc_info.value.relative_path == "sample/prompts/v2/system/story.md"


def test_no_versions_at_all_is_not_found(prompts_root):
    with pytest.raises(errors.PromptNotFoundError):
        service.load_prompt("sample/system/story")


def test_missing_file_within_existing_version_is_not_found(prompts_root):
    write_prompt(prompts_root, "sample", "v1", "system", "story", "hi")

    with pytest.raises(errors.PromptNotFoundError) as exc_info:
        service.load_prompt("sample/system/other")

    assert exc_info.value.relative_path == "sample/prompts/v1/system/other.md"


def test_bad_version_format_is_invalid(prompts_root):
    write_prompt(prompts_root, "sample", "v1", "system", "story", "text")

    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.load_prompt("sample/system/story", version="latest")

    assert exc_info.value.code == "PROMPT_ID_INVALID"
    assert exc_info.value.value == "latest"


# --- Text is verbatim; ResolvedPrompt carries the resolved version --------


def test_text_is_verbatim_no_stripping_or_normalising(prompts_root):
    raw = "  leading and trailing space \n\n"
    write_prompt(prompts_root, "sample", "v1", "system", "story", raw)

    resolved = service.load_prompt("sample/system/story")

    assert resolved.text == raw


def test_resolved_prompt_carries_capability_kind_name_and_version(prompts_root):
    path = write_prompt(prompts_root, "sample", "v1", "system", "story", "hello")

    resolved = service.load_prompt("sample/system/story")

    assert resolved == service.ResolvedPrompt(
        prompt_id="sample/system/story",
        capability="sample",
        kind="system",
        name="story",
        version="v1",
        text="hello",
        path=path,
    )


# --- Both error classes fire for their own cause (← AC4) ------------------


def test_invalid_and_not_found_are_distinguishable(prompts_root):
    write_prompt(prompts_root, "sample", "v1", "system", "story", "hi")

    with pytest.raises(errors.PromptIdInvalidError) as invalid_info:
        service.load_prompt("Sample/system/story")
    with pytest.raises(errors.PromptNotFoundError) as not_found_info:
        service.load_prompt("sample/system/missing")

    assert invalid_info.value.code == "PROMPT_ID_INVALID"
    assert not_found_info.value.code == "PROMPT_NOT_FOUND"
    assert type(invalid_info.value) is not type(not_found_info.value)


# --- Round 2, finding 1: `$` matches before a trailing newline ------------


def test_trailing_newline_in_id_is_rejected_as_invalid_with_no_filesystem_access(
    prompts_root, monkeypatch
):
    """`"sample/system/smoke\\n"` must fail PROMPT_ID_INVALID, never reach a
    `Path` at all -- a `$`-anchored grammar would let it slip past the
    whitelist and only fail later as PROMPT_NOT_FOUND."""

    def _forbidden(self):
        raise AssertionError("filesystem was accessed for a malformed id")

    monkeypatch.setattr(Path, "is_file", _forbidden)
    monkeypatch.setattr(Path, "is_dir", _forbidden)

    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.load_prompt("sample/system/smoke\n")

    assert exc_info.value.code == "PROMPT_ID_INVALID"


def test_trailing_newline_in_version_is_rejected_as_invalid_with_no_filesystem_access(
    prompts_root, monkeypatch
):
    """A `--version` of `"v1\\n"` must fail PROMPT_ID_INVALID before any
    `Path.is_file()` check, for the same `$`-before-newline reason."""
    write_prompt(prompts_root, "sample", "v1", "system", "story", "text")

    def _forbidden(self):
        raise AssertionError("filesystem was accessed for a malformed version")

    monkeypatch.setattr(Path, "is_file", _forbidden)

    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.load_prompt("sample/system/story", version="v1\n")

    assert exc_info.value.code == "PROMPT_ID_INVALID"


# --- Round 2, finding 2: text is read verbatim, not newline-translated ----


def test_text_round_trips_crlf_bytes_verbatim(prompts_root):
    """`Path.read_text()` performs universal-newline translation, turning
    `b"a\\r\\nb\\r\\n"` into `"a\\nb\\n"`. AC1 requires the file's exact
    bytes, so a CRLF prompt must come back with its `\\r\\n` intact."""
    path = prompts_root / "sample" / "prompts" / "v1" / "system" / "story.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = b"a\r\nb\r\n"
    path.write_bytes(raw)

    resolved = service.load_prompt("sample/system/story")

    assert resolved.text.encode("utf-8") == raw
    assert resolved.text == "a\r\nb\r\n"


# --- Round 2, finding 3: `list_versions` must validate `capability` too ---


def test_list_versions_rejects_a_traversal_capability(prompts_root):
    """`list_versions` is a public entry point in its own right; the
    traversal guarantee must hold here too, not only through `load_prompt`."""
    outside = prompts_root.parent / "outside"
    (outside / "prompts" / "v1").mkdir(parents=True, exist_ok=True)

    with pytest.raises(errors.PromptIdInvalidError) as exc_info:
        service.list_versions("../outside")

    assert exc_info.value.code == "PROMPT_ID_INVALID"
