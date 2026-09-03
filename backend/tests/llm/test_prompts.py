"""Tests for the Markdown prompt loader.

The point of the loader is that a missing variable is loud: a prompt with an
unfilled placeholder would reach the model as a broken instruction and come
back as a plausible-looking wrong answer.
"""

import pytest
from jinja2 import TemplateNotFound, UndefinedError

from app.llm.prompts import PROMPTS_DIR, render_prompt


def test_renders_a_prompt_with_its_variables() -> None:
    """The rendered text carries the passed value and no placeholder markup."""
    rendered = render_prompt("ping", word="pong")

    assert "pong" in rendered
    assert "{{" not in rendered


def test_suffix_is_optional() -> None:
    """`ping` and `ping.md` name the same template."""
    assert render_prompt("ping.md", word="pong") == render_prompt("ping", word="pong")


def test_missing_variable_raises() -> None:
    """A template variable the caller did not pass fails instead of rendering."""
    with pytest.raises(UndefinedError):
        render_prompt("ping")


def test_unknown_prompt_raises() -> None:
    """A prompt name without a file is a programming error, not an empty string."""
    with pytest.raises(TemplateNotFound):
        render_prompt("no-such-prompt")


def test_prompts_directory_holds_markdown_files_only() -> None:
    """Prompts live as `.md` files, so they stay reviewable and diffable."""
    files = [path for path in PROMPTS_DIR.iterdir() if path.is_file()]

    assert files
    assert [path for path in files if path.suffix != ".md"] == []
