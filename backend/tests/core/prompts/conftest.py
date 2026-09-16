"""Fixtures for `tests/core/prompts/`.

Builds a prompt tree under `tmp_path` and repoints
`service.PROMPT_MODULES_ROOT` there via `monkeypatch.setattr` — the module
attribute, never the imported name, so the monkeypatch actually takes
effect (the same rule `tests/content/conftest.py` documents for
`CONTENT_ROOT`). No test in this package depends on whatever the repo
happens to ship under `app/modules/*/prompts/`; a sibling work item seeds a
real prompt there in parallel.
"""

from pathlib import Path

import pytest

from app.core.prompts import service


def write_prompt(
    root: Path, capability: str, version: str, kind: str, name: str, text: str
) -> Path:
    """Writes `text` verbatim at `<root>/<capability>/prompts/<version>/<kind>/<name>.md`
    and returns that path."""
    path = root / capability / "prompts" / version / kind / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def prompts_root(tmp_path, monkeypatch):
    """Repoints `service.PROMPT_MODULES_ROOT` at an empty `tmp_path`."""
    monkeypatch.setattr(service, "PROMPT_MODULES_ROOT", tmp_path)
    return tmp_path
