"""Where the checkpointer's tables live, and how `alembic/env.py` leaves them
alone.

`langgraph-checkpoint-postgres` 3.1.2 emits *unqualified* table names -
`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`
- the word `schema` occurs nowhere in that package. The connection's
`search_path` is the only lever that lands them in `CHECKPOINTER_SCHEMA`
instead of `public` (`app/core/checkpointer/service.py` sets it).

Alembic must not manage those tables: it did not create them and does not
own their migrations. `include_object` is that exclusion, expressed once so
`env.py` (`app/core/checkpointer/../../alembic/env.py`) can wire it into
both `context.configure(...)` calls instead of re-deriving the predicate.

Zero third-party imports, deliberately: `env.py` imports this module at
module scope, and this module must stay importable - and testable - without
ever building a SQLAlchemy engine (`backend/tests/conftest.py` forbids
that for the whole suite)."""

CHECKPOINTER_SCHEMA = "checkpoints"


def include_object(object, name, type_, reflected, compare_to) -> bool:
    """Alembic's `include_object` hook (`EnvironmentContext.configure`):
    return `False` to exclude `object` from autogenerate comparison/DDL.
    Only the checkpointer's own schema is excluded - everything else,
    including objects with no schema at all, is left to Alembic as usual."""
    return getattr(object, "schema", None) != CHECKPOINTER_SCHEMA
