"""WI1 guard: `append_event` (`service.py`) is the only function in the
whole backend tree that constructs an `Event(...)` row (AC1). Nothing in
the schema stops a second module writing `events` directly, so this `ast`
parse is the only thing that would catch it (research.md).
"""

import ast
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2] / "app"


class _EventCallVisitor(ast.NodeVisitor):
    """Records, for every `Event(...)` call site, the name of the function
    (if any) it is written inside."""

    def __init__(self) -> None:
        self.calls_in: list[str] = []
        self._function_stack: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._function_stack.append(node.name)
        self.generic_visit(node)
        self._function_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Name) and node.func.id == "Event":
            self.calls_in.append(self._function_stack[-1] if self._function_stack else "<module>")
        self.generic_visit(node)


def test_event_constructor_appears_in_exactly_one_function():
    call_sites: set[str] = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _EventCallVisitor()
        visitor.visit(tree)
        relative = path.relative_to(APP_ROOT.parent)
        call_sites.update(f"{relative}:{fn}" for fn in visitor.calls_in)

    assert call_sites == {"app/modules/playthrough/service.py:append_event"}
