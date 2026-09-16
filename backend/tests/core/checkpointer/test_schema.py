"""Sprint 07 WI1 — `app/core/checkpointer/schema.py` (← research.md
Interfaces).

`include_object` is Alembic's exclusion predicate, and `schema.py` is
deliberately importable with zero third-party imports so this file never
builds a SQLAlchemy engine (`backend/tests/conftest.py`'s suite-wide ban) -
fabricated stand-ins play the role Alembic's real `object` argument would."""

from dataclasses import dataclass

from app.core.checkpointer.schema import CHECKPOINTER_SCHEMA, include_object


@dataclass
class _FakeSchemaObject:
    schema: str | None


def test_excludes_an_object_in_the_checkpointer_schema():
    obj = _FakeSchemaObject(schema=CHECKPOINTER_SCHEMA)
    assert include_object(obj, "checkpoints", "table", False, None) is False


def test_includes_an_object_in_another_schema():
    obj = _FakeSchemaObject(schema="public")
    assert include_object(obj, "users", "table", False, None) is True


def test_includes_an_object_with_no_schema_at_all():
    """Most reflected objects (indexes, columns) have no `.schema` attribute
    of their own - `getattr(..., None)` must not mistake absence for a
    match."""
    obj = object()
    assert include_object(obj, "ix_users_email", "index", False, None) is True
