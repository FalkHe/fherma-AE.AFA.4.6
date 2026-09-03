"""Loader for the version-controlled Markdown prompts in `app/llm/prompts/`.

Prompts are files, not strings in code and not database rows: they are
reviewable and diffable. Rendering uses Jinja with `StrictUndefined`, so a
missing variable raises instead of silently producing a prompt with a hole in
it — a half-rendered instruction is the kind of bug that only shows up as a bad
model answer.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

# .../app/llm/prompts.py -> .../app/llm/prompts/ (the module and the template
# directory are siblings; the module wins the import, the directory holds files)
PROMPTS_DIR = Path(__file__).parent / "prompts"

PROMPT_SUFFIX = ".md"


@lru_cache
def get_environment() -> Environment:
    """Return the process-wide Jinja environment for prompt templates.

    Autoescaping stays off on purpose: prompts are Markdown sent to a model,
    not HTML sent to a browser, and HTML-escaping their variables would corrupt
    the text.
    """
    return Environment(
        loader=FileSystemLoader(PROMPTS_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(name: str, /, **variables: Any) -> str:
    """Render the prompt `name` (with or without the `.md` suffix).

    Raises `jinja2.TemplateNotFound` for an unknown prompt and
    `jinja2.UndefinedError` for a variable the template uses but the caller did
    not pass — both are programming errors, never user input.
    """
    filename = name if name.endswith(PROMPT_SUFFIX) else f"{name}{PROMPT_SUFFIX}"
    return get_environment().get_template(filename).render(**variables)
