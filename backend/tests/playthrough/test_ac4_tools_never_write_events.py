"""WI1: AC4 pins, structurally, that the model can never author a
player-visible transcript line itself -- it can only choose which
mechanic runs. `append_event` (`playthrough/service.py`) is the only
writer of `events` (`test_only_event_writer.py` proves that tree-wide);
this file proves the other half of the claim: nothing in the Dungeon
Master's tool layer (`game/agent/tools.py`) reaches it, or constructs an
`Event` row, directly.

`ast`-parsed rather than imported: importing `tools.py` pulls in
`langchain_core`/`langgraph` and a real `DmContext`, none of which this
guard needs, and a source-level scan is exactly what would catch a future
tool that gains a call to `append_end`, so there is nothing an import
would additionally protect against. This is deliberately whole-file, not
scoped to functions decorated `@tool` or listed in `TOOLS` below --
research.md's own account of the module (`tools.py:1-7`, "a tool is ... a
thin call into `playthrough.service`") makes no such helper today, and a
future one, tool-only or not, must not be allowed to smuggle a write in
either."""

import ast
from pathlib import Path

TOOLS_PATH = Path(__file__).resolve().parents[2] / "app" / "modules" / "game" / "agent" / "tools.py"

WRITE_NAMES = {"append_event", "Event"}


class _WriteCallVisitor(ast.NodeVisitor):
    """Records the name of every call in the tree that matches one of
    `WRITE_NAMES` -- a bare name (`append_event(...)`) or an attribute
    (`service.append_event(...)`, `models.Event(...)`), the two forms
    `AGENTS.md` prescribes for reaching another module."""

    def __init__(self) -> None:
        self.matches: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = None
        if name in WRITE_NAMES:
            self.matches.append(name)
        self.generic_visit(node)


def _write_call_names_in_source(source: str) -> list[str]:
    visitor = _WriteCallVisitor()
    visitor.visit(ast.parse(source))
    return visitor.matches


def test_visitor_matches_a_bare_append_event_call():
    assert _write_call_names_in_source("def f():\n    append_event(a=1)\n") == ["append_event"]


def test_visitor_matches_an_attribute_append_event_call():
    assert _write_call_names_in_source("def f():\n    service.append_event(a=1)\n") == [
        "append_event"
    ]


def test_visitor_matches_an_event_construction():
    assert _write_call_names_in_source("def f():\n    models.Event(a=1)\n") == ["Event"]


def test_visitor_ignores_an_unrelated_call():
    assert _write_call_names_in_source("def f():\n    playthrough_service.take(a=1)\n") == []


def test_no_tool_in_tools_py_reaches_append_event_or_constructs_an_event():
    tree = ast.parse(TOOLS_PATH.read_text(), filename=str(TOOLS_PATH))
    visitor = _WriteCallVisitor()
    visitor.visit(tree)

    assert visitor.matches == []
