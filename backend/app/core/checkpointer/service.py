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

`checkpoint_serde()` builds the `JsonPlusSerializer` every saver in this
app uses. `langgraph-checkpoint` 3.x's msgpack layer only deserializes a
frozen dataclass it does not recognise when `allowed_msgpack_modules`
names it (or `LANGGRAPH_STRICT_MSGPACK` is unset, which just warns); the
five-node flow's own state (`app/modules/game/agent/flow_state.py`,
`effects.py`, `decisions.py`, `narration.py`) is built entirely from such
dataclasses, so every one of them is collected here by introspecting those
modules rather than hand-listing classes that drift out of sync. Both
`checkpointer()`'s `AsyncPostgresSaver` and `game/service.py`'s
`InMemorySaver()` fallback must be constructed with this same serde -
registering it on only one of the two leaves the other blocking (or
warning) on every restored turn.

Callers use the module reference (`from app.core.checkpointer import
service as checkpointer_service`), never a name import - consistent with
`app/core/llm/service.py`."""

import dataclasses
import enum
from contextlib import AbstractAsyncContextManager
from types import ModuleType
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.checkpointer.schema import CHECKPOINTER_SCHEMA
from app.core.settings import get_settings
from app.modules.game.agent import decisions as game_decisions
from app.modules.game.agent import effects as game_effects
from app.modules.game.agent import flow_state as game_flow_state
from app.modules.game.agent import narration as game_narration

_FLOW_STATE_MODULES: tuple[ModuleType, ...] = (
    game_flow_state,
    game_effects,
    game_decisions,
    game_narration,
)


def _module_dataclasses(module: ModuleType) -> list[type]:
    """Every frozen dataclass or `StrEnum` `module` defines itself (skips
    re-exports, e.g. `effects.py` importing `decisions.DecisionRequest`,
    so each type is only registered once, off the module that actually
    owns it) -- ← live bug: `OperationKind`/`DecisionKind` are `StrEnum`,
    never a dataclass, so they were never collected here even though a
    dataclass field (`Operation.kind`, `OperationSpec.kind`,
    `AwaitingRef.consumer`, ...) embeds one in nearly every checkpointed
    state; `AsyncPostgresSaver`'s own msgpack round-trip silently dropped
    every one of those fields, unlike `InMemorySaver`'s own in-process
    checkpoints, which never serialize at all and so never surfaced it."""
    return [
        member
        for member in vars(module).values()
        if isinstance(member, type)
        and (dataclasses.is_dataclass(member) or issubclass(member, enum.Enum))
        and member.__module__ == module.__name__
    ]


def checkpoint_serde() -> JsonPlusSerializer:
    """`JsonPlusSerializer` with every flow-state dataclass and enum
    registered in `allowed_msgpack_modules`, so `LANGGRAPH_STRICT_MSGPACK=
    true` blocks genuinely unrecognised types without blocking this
    flow's own."""
    allowed: list[type] = []
    for module in _FLOW_STATE_MODULES:
        allowed.extend(_module_dataclasses(module))
    return JsonPlusSerializer(allowed_msgpack_modules=allowed)


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
    return AsyncPostgresSaver.from_conn_string(conn_string, serde=checkpoint_serde())


async def ensure_schema() -> None:
    """`CREATE SCHEMA IF NOT EXISTS` for `CHECKPOINTER_SCHEMA` - the step
    `AsyncPostgresSaver.setup()` never performs itself."""
    conn_string = checkpointer_conn_string(get_settings().database_url)
    async with await psycopg.AsyncConnection.connect(conn_string) as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINTER_SCHEMA}")


async def setup() -> None:
    """Make the checkpointer usable: the schema, then its tables."""
    await ensure_schema()
    async with checkpointer() as saver:
        await saver.setup()
