"""Guard over every prompt shipped under `app/modules/*/prompts/`.

Deliberately unmocked: this walks the real repository tree, not a
`tmp_path` fixture, because the whole point is to catch a file that some
later change drops at a path the resolver cannot reach. A prompt that
exists on disk but is unreachable is worse than no prompt at all -- it
looks present.

Criteria (sprint 06, WI3):
- every file under `app/modules/*/prompts/` is a `.md` file,
- it sits at exactly `<capability>/prompts/v<n>/<kind>/<id>.md`,
- every path segment satisfies the resolver's grammar (enforced by
  `load_prompt` itself -- a malformed segment makes it raise), and
- it actually resolves through `prompt_service.load_prompt(...)`, and the
  resolved text is byte-for-byte the file's own content.
"""

from pathlib import Path

import pytest

from app.core.prompts import service as prompt_service
from app.core.prompts.errors import PromptError

MODULES_ROOT: Path = prompt_service.PROMPT_MODULES_ROOT


def _shipped_prompt_files() -> list[Path]:
    return sorted(p for p in MODULES_ROOT.glob("*/prompts/**/*") if p.is_file())


def test_at_least_one_prompt_is_shipped():
    # Sanity check on the walk itself: an empty result would make every
    # other assertion in this file vacuously true.
    assert _shipped_prompt_files(), f"no prompt files found under {MODULES_ROOT}/*/prompts/"


@pytest.mark.parametrize("path", _shipped_prompt_files(), ids=lambda p: str(p))
def test_shipped_prompt_is_reachable_c_wi3(path: Path):
    relative = path.relative_to(MODULES_ROOT)

    assert path.suffix == ".md", f"shipped prompt is not a .md file: {relative}"

    parts = relative.parts
    assert len(parts) == 5 and parts[1] == "prompts", (
        f"shipped prompt is not at <capability>/prompts/v<n>/<kind>/<id>.md: {relative}"
    )

    capability, _prompts, version, kind, filename = parts
    name = filename.removesuffix(".md")
    prompt_id = f"{capability}/{kind}/{name}"

    try:
        resolved = prompt_service.load_prompt(prompt_id, version=version)
    except PromptError as exc:
        pytest.fail(f"shipped prompt does not resolve: {relative} ({exc})")

    assert resolved.text == path.read_text(), (
        f"resolved text does not match the shipped file verbatim: {relative}"
    )
    assert resolved.version == version, f"resolved to the wrong version: {relative}"
