"""Sprint 07 WI2 -- Alembic ignores the checkpointer's schema, deliberately
rather than incidentally (<- research.md Interfaces; AC4/AC6).

Two independent proofs, since `env.py` itself can never be imported by this
suite: it builds a real engine and calls `run_migrations_online()` at module
scope, both forbidden by `backend/tests/conftest.py`'s suite-wide ban.

1. `include_object` as a pure function -- fabricated stand-ins play the role
   of Alembic's real `object` argument, so the predicate itself never needs
   a `Table`.
2. `env.py`, parsed as text with `ast`, actually wires `include_schemas=True`
   and `include_object` into *both* `context.configure(...)` calls, and
   imports `include_object` from `app.core.checkpointer.schema` rather than
   defining it locally. Without `include_schemas=True`, autogenerate never
   looks at other schemas in the first place and the predicate is never
   exercised -- the exclusion would be incidental, not deliberate, and would
   silently evaporate the moment anything else set that flag. This is also
   what catches a future edit that drops one of the two calls: a test that
   only exercises the function would stay green while the wiring rotted."""

import ast
from dataclasses import dataclass
from pathlib import Path

from app.core.checkpointer.schema import CHECKPOINTER_SCHEMA, include_object

ENV_PY = Path(__file__).resolve().parents[3] / "alembic" / "env.py"

# (function in env.py, human label for assertion messages)
_CONFIGURE_SITES = [
    ("run_migrations_offline", "the offline context.configure() call (run_migrations_offline)"),
    ("do_run_migrations", "the online context.configure() call (do_run_migrations)"),
]


@dataclass
class _FakeSchemaObject:
    schema: str | None


def test_excludes_an_object_in_the_checkpointer_schema():
    obj = _FakeSchemaObject(schema=CHECKPOINTER_SCHEMA)
    assert include_object(obj, "checkpoints", "table", False, None) is False


def test_includes_an_object_in_the_public_schema():
    obj = _FakeSchemaObject(schema="public")
    assert include_object(obj, "users", "table", False, None) is True


def test_includes_an_object_with_no_schema_at_all():
    """Most reflected objects (indexes, columns) have no schema of their
    own; `None` must not be mistaken for a match against the checkpointer's
    schema name."""
    obj = _FakeSchemaObject(schema=None)
    assert include_object(obj, "ix_users_email", "index", False, None) is True


def test_includes_an_object_in_some_other_schema():
    obj = _FakeSchemaObject(schema="analytics")
    assert include_object(obj, "events", "table", False, None) is True


def _parse_env_py() -> ast.Module:
    return ast.parse(ENV_PY.read_text(), filename=str(ENV_PY))


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"env.py has no function named {name!r}")


def _find_configure_call(func_node: ast.FunctionDef, label: str) -> ast.Call:
    calls = [
        node
        for node in ast.walk(func_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "configure"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "context"
    ]
    assert len(calls) == 1, (
        f"expected exactly one context.configure(...) call inside {label}, found {len(calls)}"
    )
    return calls[0]


def _keyword_value(call: ast.Call, name: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return None


def test_include_object_is_imported_from_the_shared_schema_module():
    """env.py must not re-derive the predicate locally -- it wires the one
    `app.core.checkpointer.schema` already defines."""
    tree = _parse_env_py()

    imports_it = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "app.core.checkpointer.schema"
        and any(alias.name == "include_object" for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_it, "env.py must import include_object from app.core.checkpointer.schema"

    defines_it_locally = any(
        isinstance(node, ast.FunctionDef) and node.name == "include_object"
        for node in ast.walk(tree)
    )
    assert not defines_it_locally, (
        "include_object must not be redefined locally in env.py -- "
        "it must come from app.core.checkpointer.schema"
    )


def test_both_configure_calls_carry_include_schemas_true_and_include_object():
    tree = _parse_env_py()

    for function_name, label in _CONFIGURE_SITES:
        func_node = _find_function(tree, function_name)
        call = _find_configure_call(func_node, label)

        include_schemas = _keyword_value(call, "include_schemas")
        assert include_schemas is not None, f"{label} is missing include_schemas=True"
        assert isinstance(include_schemas, ast.Constant) and include_schemas.value is True, (
            f"{label} must pass include_schemas=True literally, got {ast.dump(include_schemas)}"
        )

        include_object_kw = _keyword_value(call, "include_object")
        assert include_object_kw is not None, f"{label} is missing include_object"
        wires_shared_predicate = (
            isinstance(include_object_kw, ast.Name) and include_object_kw.id == "include_object"
        )
        assert wires_shared_predicate, (
            f"{label} must pass the imported include_object, got {ast.dump(include_object_kw)}"
        )
