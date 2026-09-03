"""In-memory fake `AsyncSession` for the service-layer tests.

`StubSession` in the top-level `conftest.py` only records `execute()` calls for
route-level tests that never inspect a result. The services genuinely read back
what they write (uniqueness checks, session lookups, spec upserts), so this
fixture is a small in-memory store instead: it interprets the handful of
`select`/`delete`/`update` shapes the services actually issue, without ever
opening a real database connection or event loop of its own — everything here
is plain `async def` called from the test's own `asyncio.run()`.

Supported: `select`/`delete`/`update` against a single mapped entity, `where`
clauses built from `==`/`!=`/`IN`/`IS` comparisons of a column against a literal
(or `NULL`) combined with `AND`, `order_by` over the same kind of expressions,
`limit` / `offset`, `select(func.count())` over one table, and
`select(func.pg_notify(channel, payload))` (recorded in `.notifications`, so the
"commit first, then notify" ordering is observable). Anything else raises
`NotImplementedError` loudly rather than silently matching nothing, so a future
service change this fixture cannot interpret fails fast instead of pretending to
pass.

Server defaults are simulated for **timestamp columns only** (`created_at` /
`updated_at` are stamped on `add`, because endpoint responses carry them);
everything else — enum and JSONB defaults — is set by the services in Python.
"""

import operator
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import BinaryExpression, DateTime, Delete, Select, Update
from sqlalchemy.sql.elements import (
    BindParameter,
    BooleanClauseList,
    ColumnClause,
    Null,
    UnaryExpression,
)
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.operators import and_, desc_op, eq, in_op, is_, is_not, ne

from app.db.models.base import Base, new_ulid
from app.db.models.session import Session
from app.db.models.user import User

_COMPARISONS = {
    eq: operator.eq,
    ne: operator.ne,
    in_op: lambda left, right: left in right,
    # `column.is_(None)` / `.is_not(None)` — the soft-delete and supersession
    # filters of `chat_service`.
    is_: operator.is_,
    is_not: operator.is_not,
}


@dataclass
class _FakeScalars:
    rows: list[Any]

    def all(self) -> list[Any]:
        return self.rows


@dataclass
class _FakeResult:
    rows: list[Any]

    def scalar_one_or_none(self) -> Any | None:
        if not self.rows:
            return None
        assert len(self.rows) == 1, "fake store matched more than one row"
        return self.rows[0]

    def scalar_one(self) -> Any:
        assert len(self.rows) == 1, "fake store did not match exactly one row"
        return self.rows[0]

    def scalars(self) -> _FakeScalars:
        return _FakeScalars(self.rows)


class FakeAsyncSession:
    """Interprets the exact statement shapes used by the services."""

    def __init__(self) -> None:
        self.stores: dict[type[Any], dict[str, Any]] = {}
        self.commit_count = 0
        self.deleted_objects: list[Any] = []
        # Every `pg_notify(channel, payload)` the services issued, in order.
        self.notifications: list[tuple[str, str]] = []

    @property
    def users(self) -> dict[str, User]:
        return self.store(User)

    @property
    def sessions(self) -> dict[str, Session]:
        return self.store(Session)

    def store(self, entity: type[Any]) -> dict[str, Any]:
        """Return the row store of one mapped class, creating it on first use."""
        return self.stores.setdefault(entity, {})

    def rows(self, entity: type[Any]) -> list[Any]:
        """Return every stored row of one mapped class, in insertion order."""
        return list(self.store(entity).values())

    def add(self, obj: Any) -> None:
        """Mimic ORM flush-time PK assignment and timestamps, then insert."""
        if not isinstance(obj, Base):  # pragma: no cover - defensive
            raise TypeError(f"FakeAsyncSession.add: unsupported type {type(obj)!r}")
        if getattr(obj, "id", None) is None:
            obj.id = new_ulid()
        self._stamp_timestamps(obj)
        self.store(type(obj))[obj.id] = obj

    @staticmethod
    def _stamp_timestamps(obj: Any) -> None:
        """Fill server-defaulted timestamp columns, as the database would."""
        now = datetime.now(UTC)
        for column in obj.__table__.columns:
            if (
                column.server_default is not None
                and isinstance(column.type, DateTime)
                and getattr(obj, column.key, None) is None
            ):
                setattr(obj, column.key, now)

    async def commit(self) -> None:
        self.commit_count += 1

    async def flush(self) -> None:
        """No-op: `add` already inserted the row and assigned its id."""

    async def refresh(self, obj: Any) -> None:
        """No-op: the store hands out live objects, nothing ever expires."""

    async def delete(self, obj: Any) -> None:
        self.deleted_objects.append(obj)
        self.store(type(obj)).pop(obj.id, None)

    async def execute(self, statement: object) -> _FakeResult:
        if isinstance(statement, Select):
            return self._execute_select(statement)
        if isinstance(statement, Delete):
            return self._execute_delete(statement)
        if isinstance(statement, Update):
            return self._execute_update(statement)
        raise NotImplementedError(f"FakeAsyncSession.execute: unsupported statement {statement!r}")

    def _execute_select(self, statement: Select) -> _FakeResult:
        description = statement.column_descriptions[0]
        # A projection that is not a mapped entity (a function) carries no
        # `entity` key at all when it is not an ORM-enabled select.
        if description.get("entity") is None:
            return self._execute_function(statement, description["expr"])

        rows = self._filter(self.rows(description["entity"]), statement.whereclause)
        for clause in reversed(statement._order_by_clauses):
            rows = self._sorted(rows, clause)
        return _FakeResult(self._paginated(rows, statement))

    def _execute_function(self, statement: Select, expression: object) -> _FakeResult:
        """Interpret the two function projections the services select."""
        if not isinstance(expression, Function):
            raise NotImplementedError(f"FakeAsyncSession: unsupported projection {expression!r}")
        if expression.name == "count":
            entity = self._entity_of(statement.get_final_froms()[0].name)
            return _FakeResult([len(self._filter(self.rows(entity), statement.whereclause))])
        if expression.name == "pg_notify":
            channel, payload = (self._value(part, None) for part in expression.clauses)
            self.notifications.append((channel, payload))
            return _FakeResult([None])
        raise NotImplementedError(f"FakeAsyncSession: unsupported function {expression!r}")

    @classmethod
    def _paginated(cls, rows: list[Any], statement: Select) -> list[Any]:
        offset = cls._bound_value(statement._offset_clause)
        limit = cls._bound_value(statement._limit_clause)
        if offset is not None:
            rows = rows[offset:]
        if limit is not None:
            rows = rows[:limit]
        return rows

    @classmethod
    def _bound_value(cls, clause: object) -> Any | None:
        return None if clause is None else cls._value(clause, None)

    def _execute_delete(self, statement: Delete) -> _FakeResult:
        store = self.store(self._entity_of(statement.table.name))
        for obj in self._filter(list(store.values()), statement.whereclause):
            store.pop(obj.id, None)
        return _FakeResult([])

    def _execute_update(self, statement: Update) -> _FakeResult:
        entity = self._entity_of(statement.table.name)
        matches = self._filter(self.rows(entity), statement.whereclause)
        for column, value in statement._values.items():
            for obj in matches:
                setattr(obj, column.key, self._value(value, obj))
        return _FakeResult([])

    @staticmethod
    def _entity_of(table_name: str) -> type[Any]:
        for mapper in Base.registry.mappers:
            if mapper.local_table is not None and mapper.local_table.name == table_name:
                return mapper.class_
        raise NotImplementedError(f"FakeAsyncSession: no mapped class for table {table_name!r}")

    @classmethod
    def _filter(cls, rows: list[Any], whereclause: object) -> list[Any]:
        if whereclause is None:
            return rows
        return [row for row in rows if cls._value(whereclause, row)]

    @classmethod
    def _sorted(cls, rows: list[Any], clause: object) -> list[Any]:
        # `.desc()` is the only descending modifier; `.asc()` and a bare column
        # both sort ascending.
        descending = isinstance(clause, UnaryExpression) and clause.modifier is desc_op
        key = clause.element if isinstance(clause, UnaryExpression) else clause
        return sorted(rows, key=lambda row: cls._value(key, row), reverse=descending)

    @classmethod
    def _value(cls, clause: object, row: Any) -> Any:
        """Evaluate one SQL expression against a stored row, in Python."""
        if isinstance(clause, BindParameter):
            return clause.value
        if isinstance(clause, Null):
            # The right-hand side of `column.is_(None)`.
            return None
        if isinstance(clause, BooleanClauseList):
            if clause.operator is not and_:
                raise NotImplementedError(f"FakeAsyncSession: unsupported junction {clause!r}")
            return all(cls._value(part, row) for part in clause.clauses)
        if isinstance(clause, BinaryExpression):
            comparison = _COMPARISONS.get(clause.operator)
            if comparison is None:
                raise NotImplementedError(f"FakeAsyncSession: unsupported operator {clause!r}")
            return comparison(cls._value(clause.left, row), cls._value(clause.right, row))
        if isinstance(clause, ColumnClause):
            return getattr(row, clause.key)
        raise NotImplementedError(f"FakeAsyncSession: unsupported expression {clause!r}")


@pytest.fixture
def fake_session() -> Iterator[FakeAsyncSession]:
    yield FakeAsyncSession()
