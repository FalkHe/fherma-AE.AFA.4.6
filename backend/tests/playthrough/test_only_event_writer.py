"""WI1 guard: `append_event` (`service.py`) is the only function in the
whole backend tree that constructs an `Event` row (AC1). Nothing in the
schema stops a second module writing `events` directly, so this `ast`
parse is the only thing that would catch it (research.md).

Matches both construction forms: a bare `Event(...)` (`ast.Name`) and
`<module>.Event(...)` (`ast.Attribute`) -- the latter is the form
`AGENTS.md` prescribes for reaching another module ("only its
`service.py` / `models.py`"), so it is exactly the shape a future
sprint's mechanic would naturally write when it calls
`models.Event(...)` directly instead of going through `append_event`.
`test_visitor_matches_*` below prove the visitor itself catches each form
on a small source string, rather than trusting the tree-wide scan alone
to ever have exercised the failure path.
"""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class _EventCallVisitor(ast.NodeVisitor):
    """Records, for every `Event(...)` construction -- bare-name or
    attribute -- the name of the function (if any) it is written inside."""

    def __init__(self) -> None:
        self.calls_in: list[str] = []
        self._function_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        else:
            name = None
        if name == "Event":
            self.calls_in.append(self._function_stack[-1] if self._function_stack else "<module>")
        self.generic_visit(node)


def _event_call_sites_in_source(source: str) -> list[str]:
    """Every enclosing-function name the visitor records for `source`
    (`"<module>"` for a call at top level) -- the unit the two
    `test_visitor_matches_*` tests below exercise directly, without
    touching the filesystem."""
    visitor = _EventCallVisitor()
    visitor.visit(ast.parse(source))
    return visitor.calls_in


def test_visitor_matches_bare_name_construction():
    assert _event_call_sites_in_source("def f():\n    Event(a=1)\n") == ["f"]


def test_visitor_matches_attribute_construction():
    # The `models.Event(...)` form AGENTS.md prescribes for reaching
    # another module -- the exact shape the tree-wide scan below must
    # not miss.
    assert _event_call_sites_in_source("def f():\n    models.Event(a=1)\n") == ["f"]


def test_visitor_ignores_an_unrelated_call_named_differently():
    assert _event_call_sites_in_source("def f():\n    EventFactory(a=1)\n") == []


def test_event_constructor_appears_in_exactly_one_function():
    call_sites: set[str] = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _EventCallVisitor()
        visitor.visit(tree)
        relative = path.relative_to(APP_ROOT.parent)
        call_sites.update(f"{relative}:{fn}" for fn in visitor.calls_in)

    assert call_sites == {"app/modules/playthrough/service.py:append_event"}
