"""The seam between this app and LangGraph's Postgres checkpointer.

`checkpointer_conn_string()` turns the app's `DATABASE_URL` (a SQLAlchemy
URL, `postgresql+psycopg://...`) into a libpq conninfo string pinned to
`CHECKPOINTER_SCHEMA` via the connection's `search_path` - the only lever
that works, since `langgraph-checkpoint-postgres` 3.1.2 emits unqualified
table names (`app/core/checkpointer/schema.py`'s docstring). The `+psycopg`
driver tag must be stripped: `AsyncPostgresSaver` hands the string straight
to `psycopg.AsyncConnection.connect`, which rejects the SQLAlchemy-style
prefix loudly (`psycopg.ProgrammingError: missing "=" after ...`).

`checkpointer()` is a bare `from_conn_string(...)` passthrough - callers
`async with checkpointer() as saver:` to get an `AsyncPostgresSaver`.

`ensure_schema()` exists because `AsyncPostgresSaver.setup()` does **not**
create the schema it needs - only the tables inside it, once the schema is
already on the `search_path`. `setup()` therefore always runs
`ensure_schema()` first; calling it twice is a verified no-op.

Callers use the module reference (`from app.core.checkpointer import
service as checkpointer_service`), never a name import - consistent with
`app/core/llm/service.py`."""

from contextlib import AbstractAsyncContextManager
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.core.checkpointer.schema import CHECKPOINTER_SCHEMA
from app.core.settings import get_settings


def checkpointer_conn_string(database_url: str) -> str:
    """Strip the SQLAlchemy `+<driver>` tag off `database_url`'s scheme and
    pin the connection's `search_path` to `CHECKPOINTER_SCHEMA` via the
    libpq `options` query parameter. Any query parameters already present
    on `database_url` are preserved ahead of `options`."""
    parts = urlsplit(database_url)
    scheme = parts.scheme.split("+", 1)[0]
    query_pairs = [
        *parse_qsl(parts.query, keep_blank_values=True),
        ("options", f"-csearch_path={CHECKPOINTER_SCHEMA}"),
    ]
    query = urlencode(query_pairs)
    return urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))


def checkpointer() -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    """`AsyncPostgresSaver.from_conn_string(...)` passthrough, pointed at
    this app's database via the current settings."""
    conn_string = checkpointer_conn_string(get_settings().database_url)
    return AsyncPostgresSaver.from_conn_string(conn_string)


async def ensure_schema() -> None:
    """`CREATE SCHEMA IF NOT EXISTS` for `CHECKPOINTER_SCHEMA` - the step
    `AsyncPostgresSaver.setup()` never performs itself."""
    conn_string = checkpointer_conn_string(get_settings().database_url)
    async with psycopg.AsyncConnection.connect(conn_string) as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINTER_SCHEMA}")


async def setup() -> None:
    """Make the checkpointer usable: the schema, then its tables."""
    await ensure_schema()
    async with checkpointer() as saver:
        await saver.setup()
