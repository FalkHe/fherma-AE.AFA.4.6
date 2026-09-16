"""Resolves a prompt id, plus an optional version, to prompt text.

Layout: `<PROMPT_MODULES_ROOT>/<capability>/prompts/<version>/<kind>/<id>.md`.
Cross-capability by construction (phase 7's character agent and phase 8's
DM both call this), so it lives in `core/`, not in a module — a module home
would force module→module imports, which `AGENTS.md` forbids.

**The grammar is the security boundary.** An id is split on `/` into
exactly three segments, each checked against `_SEGMENT` *before any `Path`
is built*. A segment admits no `.`, no `/`, no empty string, no uppercase,
no leading or trailing hyphen — so `..`, `a/../b` and an absolute path are
unrepresentable, not merely rejected after the fact. There is deliberately
no `resolve()` containment check as a second line of defence: if the
grammar is right that check is unnecessary, and a redundant one invites a
future reader to loosen the grammar believing the check will still save
them.

**No fallback.** `load_prompt(prompt_id, version=None)` resolves to the
numerically highest version (`int(v[1:])`, so `v10` beats `v9` — lexical
sort would be a bug); a version passed explicitly is used as given, and a
missing requested version is `PromptNotFoundError`, never silently swapped
for another one (D5: that would change a playthrough's prompt underfoot).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.prompts.errors import PromptIdInvalidError, PromptNotFoundError

PROMPT_MODULES_ROOT: Path = Path(__file__).resolve().parents[2] / "modules"

_SEGMENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
VERSION_PATTERN = re.compile(r"^v[0-9]+$")


@dataclass(frozen=True)
class ResolvedPrompt:
    prompt_id: str
    capability: str
    kind: str
    name: str
    version: str
    text: str
    path: Path


def parse_prompt_id(prompt_id: str) -> tuple[str, str, str]:
    """Splits `prompt_id` into `(capability, kind, name)`.

    Raises `PromptIdInvalidError` unless the id is exactly three segments,
    each matching `_SEGMENT` — checked before any `Path` is constructed, so
    a malformed id (including any traversal attempt) never reaches the
    filesystem.
    """
    segments = prompt_id.split("/")
    if len(segments) != 3:
        raise PromptIdInvalidError(prompt_id, "must have exactly three segments")
    for segment in segments:
        if not _SEGMENT.match(segment):
            raise PromptIdInvalidError(prompt_id, f"segment '{segment}' is not lowercase-kebab")
    capability, kind, name = segments
    return capability, kind, name


def list_versions(capability: str) -> list[str]:
    """Every `v<n>` directory under `<capability>/prompts/`, ascending by
    `int(v[1:])`. `[]` if the capability or its `prompts/` directory does
    not exist.
    """
    prompts_dir = PROMPT_MODULES_ROOT / capability / "prompts"
    if not prompts_dir.is_dir():
        return []
    versions = [
        entry.name
        for entry in prompts_dir.iterdir()
        if entry.is_dir() and VERSION_PATTERN.match(entry.name)
    ]
    versions.sort(key=lambda v: int(v[1:]))
    return versions


def load_prompt(prompt_id: str, *, version: str | None = None) -> ResolvedPrompt:
    """Resolves `prompt_id` to its text at `version`, or at the numerically
    highest available version when `version` is `None`.

    Raises `PromptIdInvalidError` for a malformed id or a `version` that
    fails `VERSION_PATTERN`; `PromptNotFoundError` for a well-formed id
    whose capability directory, `prompts/`, version directory or `<id>.md`
    is missing. A requested version that does not exist is `NotFound`,
    never a fallback to another one.
    """
    capability, kind, name = parse_prompt_id(prompt_id)

    if version is not None and not VERSION_PATTERN.match(version):
        raise PromptIdInvalidError(version, "does not match v<n>")

    resolved_version = version
    if resolved_version is None:
        versions = list_versions(capability)
        if not versions:
            raise PromptNotFoundError(f"{capability}/prompts")
        resolved_version = versions[-1]

    relative_path = f"{capability}/prompts/{resolved_version}/{kind}/{name}.md"
    path = PROMPT_MODULES_ROOT / capability / "prompts" / resolved_version / kind / f"{name}.md"
    if not path.is_file():
        raise PromptNotFoundError(relative_path)

    text = path.read_text()
    return ResolvedPrompt(
        prompt_id=prompt_id,
        capability=capability,
        kind=kind,
        name=name,
        version=resolved_version,
        text=text,
        path=path,
    )
