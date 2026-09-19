"""qa acceptance tests -- sprint 005/05b "the run reports its cost and says
when something is new"
(`docs/intents/005-game-state-services/sprints/05b-cost-and-live-signal/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`'s
`run_cost`/stream internals, `app.modules.playthrough.commands` or the
stream route itself -- those are this sprint's own work items, written in
parallel, and this file never reads them. `service.latest_event_id` and
`service.run_cost` are used only as the plan's own named seams (I1, I3),
called or monkeypatched exactly as any other black-box caller would.

AC3 carries `@pytest.mark.database` (plan.md's own instruction: "the cost
sums @pytest.mark.database"): the exact per-run and per-turn decimal sums,
with the untagged group last, are proven against the real scratch database
(`playthrough_db`) by calling `run_cost` directly -- never through the CLI,
because the CLI opens its own session via the process-wide, `lru_cache`d
`get_sessionmaker()` (`research.md` "CLI"), which must never be pointed at a
scratch database (`tests/database.py`'s own warning). The command's I/O
contract -- the exact stdout format and the `NOT_FOUND` stderr refusal -- is
instead proven engine-free, driving the real `cli` through `CliRunner` with
`playthrough_service.run_cost` monkeypatched, exactly like
`tests/srd/test_commands.py`'s style. "No HTTP route exposes cost" is
checked against the live OpenAPI document and a real 404 on `.../cost`,
which needs no database either -- everything in this file runs under one
`@pytest.mark.database` umbrella regardless, matching this suite's own
`test_acceptance_event_stream.py` AC2 precedent of mixing a database-backed
half and a mocked half in one test function.

AC4 needs no database at all: the plan documents membership as checked
through the same `latest_event_id(db, *, user_id, run_id)` seam that also
drives the per-tick signal (I3), so mocking that one function proves the
refusal, the `updated` message, the keepalive comment and the lifetime
bound, all without a real member row. The disconnect path is proven by
monkeypatching `starlette.requests.Request.is_disconnected` itself (the
exact hook I3 names: "The loop ends on `await request.is_disconnected()`")
rather than by fishing a bare generator out of routes.py's internals --
this sprint's FastAPI/Starlette pin (0.141.1 / 1.6.0) restructures router
internals well past anything this suite's other files rely on, so reaching
into them here would test this file's guess at that structure, not the
sprint's contract. Both settings (`sse_poll_interval_seconds`,
`sse_max_lifetime_seconds`) are pinned small around every streaming call,
via env vars plus `get_settings.cache_clear()` on the way in and out, never
leaking into another scenario or another test file.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas); the one real-database
scenario wraps its async calls in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
commands or route themselves -- this suite is red until the corresponding
work items land, and green once they do.
"""

import asyncio
import inspect
import json
import os
import time
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from typing import Annotated, get_args, get_origin, get_type_hints

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.requests import Request
from typer.testing import CliRunner

from app.cli import cli
from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.core.settings import get_settings
from app.main import create_app
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import AuthContext
from app.modules.playthrough import service as playthrough_service
from app.modules.playthrough.errors import CampaignRunNotFoundError
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

runner = CliRunner()

USER_ID = generate_id()
CSRF_TOKEN = "the-matching-csrf-token"  # noqa: S105 - fixture value, not a secret


def _stub_auth(monkeypatch_ctx, *, user_id: str = USER_ID, csrf_token: str = CSRF_TOKEN) -> None:
    """Identical in shape to `test_acceptance_transcript_writer_and_read
    .py`'s `_stub_auth` -- resolves the session cookie to a user without a
    database, so every mocked scenario below needs no real member row."""
    session = make_session(user_id=user_id, csrf_token=csrf_token)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch_ctx.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch_ctx.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


async def _insert_cost_event(
    session, event_id: str, campaign_run_id: str, *, turn_id: str | None, cost_usd: Decimal
) -> None:
    """One `events` row carrying only what `run_cost` (I1) needs: a
    `campaign_run_id`, a `turn_id` (full-length, never a short literal --
    `turn_id` is `CHAR(26)`, which pads short literals on read, `research.md`
    "Id ordering") and a `cost_usd`. `type`/`visibility` are fixed to values
    that satisfy the table's own CHECK constraints and are never filtered by
    this sprint's cost report (05a's own `SUM(cost_usd)` acceptance test,
    `test_acceptance_event_stream.py` AC4, sums with no visibility filter
    either)."""
    await session.execute(
        text(
            "INSERT INTO events (id, campaign_run_id, type, visibility, payload, turn_id, "
            "cost_usd) VALUES (:id, :campaign_run_id, 'system', 'player', '{}'::jsonb, "
            ":turn_id, :cost_usd)"
        ),
        {
            "id": event_id,
            "campaign_run_id": campaign_run_id,
            "turn_id": turn_id,
            "cost_usd": cost_usd,
        },
    )


@pytest.mark.database
def test_ac3_the_command_reports_exact_decimal_sums_grouped_by_turn_with_untagged_last(
    client, assert_error_envelope, playthrough_db
):
    # <- AC3

    # -- The exact sums, for the owner, against the real database: `run_cost`
    # (I1) called directly, never through the CLI (see module docstring).
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac3-owner")
        await _insert_user(playthrough_db, stranger_id, username="ac3-stranger")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )

        turn_a = generate_id()
        turn_b = generate_id()

        # Many small charges, deliberately not round numbers, so an exact
        # `Decimal` equality check is the only thing that could pass --
        # a naive float accumulation is never trusted here (← AC3, the
        # criterion's own point).
        charges = [
            (turn_a, Decimal("0.000123")),
            (turn_a, Decimal("0.000002")),
            (turn_a, Decimal("0.000375")),  # turn_a total: 0.000500
            (turn_b, Decimal("0.250001")),
            (turn_b, Decimal("0.999999")),  # turn_b total: 1.250000
            (None, Decimal("0.000734")),
            (None, Decimal("0.000266")),  # untagged total: 0.001000
        ]
        for turn_id, cost in charges:
            await _insert_cost_event(
                playthrough_db, generate_id(), run.id, turn_id=turn_id, cost_usd=cost
            )
        await playthrough_db.commit()

        result = await playthrough_service.run_cost(playthrough_db, user_id=owner_id, run_id=run.id)

        assert isinstance(result.total, Decimal)
        assert result.total == Decimal("1.251500")

        by_turn = {turn.turn_id: turn.total for turn in result.turns}
        assert isinstance(by_turn[turn_a], Decimal)
        assert by_turn[turn_a] == Decimal("0.000500")
        assert by_turn[turn_b] == Decimal("1.250000")
        assert by_turn[None] == Decimal("0.001000")

        # The entries belonging to no turn are grouped last.
        assert result.turns[-1].turn_id is None
        assert result.turns[-1].total == Decimal("0.001000")

        # Empty sums read as zero, not as nothing: a run with no
        # cost-bearing events at all.
        second_run_id = generate_id()
        await playthrough_db.execute(
            text(
                "INSERT INTO campaign_runs (id, campaign_id, content_version) "
                "VALUES (:id, 'greenhollow', 'v1')"
            ),
            {"id": second_run_id},
        )
        await playthrough_db.execute(
            text(
                "INSERT INTO campaign_run_members (id, campaign_run_id, user_id) "
                "VALUES (:id, :campaign_run_id, :user_id)"
            ),
            {"id": generate_id(), "campaign_run_id": second_run_id, "user_id": owner_id},
        )
        await playthrough_db.commit()

        empty_result = await playthrough_service.run_cost(
            playthrough_db, user_id=owner_id, run_id=second_run_id
        )
        assert isinstance(empty_result.total, Decimal)
        assert empty_result.total == Decimal("0.000000")

        # A user who is not a member of the game gets `NOT_FOUND`.
        with pytest.raises(Exception) as exc_info:
            await playthrough_service.run_cost(playthrough_db, user_id=stranger_id, run_id=run.id)
        assert exc_info.value.code == ErrorCode.NOT_FOUND

    asyncio.run(_scenario())

    # -- The command's I/O contract: exact stdout, exit 0 -- driven through
    # `CliRunner` against the real `cli`, with `run_cost` monkeypatched so
    # no database is touched here (`tests/srd/test_commands.py`'s style).
    # Reset by its own `MonkeyPatch.context()` before the refusal case runs.
    with pytest.MonkeyPatch.context() as mp:
        run_id = generate_id()
        turn_id = generate_id()

        async def fake_run_cost(db, *, user_id, run_id):
            return SimpleNamespace(
                total=Decimal("0.001234"),
                turns=[
                    SimpleNamespace(turn_id=turn_id, total=Decimal("0.000500")),
                    SimpleNamespace(turn_id=None, total=Decimal("0.000734")),
                ],
            )

        mp.setattr(playthrough_service, "run_cost", fake_run_cost)

        result = runner.invoke(cli, ["playthrough", "cost", run_id, "--user", USER_ID])

        assert result.exit_code == 0, result.output
        assert result.stderr == ""
        expected_stdout = (
            f"run: {run_id}\ntotal: 0.001234\nturn {turn_id}: 0.000500\nturn -: 0.000734\n"
        )
        assert result.stdout == expected_stdout

    # -- A foreign run answers `NOT_FOUND` on stderr, exit 1. Its own scope,
    # so the format-test's monkeypatch above is never in effect here.
    with pytest.MonkeyPatch.context() as mp:
        refused_run_id = generate_id()

        async def failing_run_cost(db, *, user_id, run_id):
            raise CampaignRunNotFoundError(run_id)

        mp.setattr(playthrough_service, "run_cost", failing_run_cost)

        result = runner.invoke(cli, ["playthrough", "cost", refused_run_id, "--user", USER_ID])

        assert result.exit_code == 1, result.output
        assert result.stdout == ""
        assert result.stderr.strip() == f"NOT_FOUND: campaign run not found: {refused_run_id}"

    # -- No HTTP route exposes cost: no path, operation id, schema name or
    # schema property in the live OpenAPI document names it. Checked
    # structurally (paths, schema names, property names), never as a raw
    # substring scan of the whole document -- prose `description` text is
    # free to talk *about* the decision not to expose cost (the module's own
    # docs do, deliberately), and that must never look like a violation.
    openapi_response = client.get("/openapi.json")
    assert openapi_response.status_code == 200, openapi_response.text
    openapi_document = openapi_response.json()

    for path, operations in openapi_document["paths"].items():
        assert "cost" not in path.lower(), path
        for operation in operations.values():
            if isinstance(operation, dict):
                assert "cost" not in str(operation.get("operationId", "")).lower(), path

    schemas = openapi_document.get("components", {}).get("schemas", {})
    for name, schema in schemas.items():
        assert "cost" not in name.lower(), name
        for property_name in schema.get("properties", {}):
            assert "cost" not in property_name.lower(), (name, property_name)

    cost_response = client.get(f"/api/v1/playthrough/campaign/{generate_id()}/cost")
    assert_error_envelope(cost_response, status=404, code="NOT_FOUND")


@contextmanager
def _pinned_sse_settings(*, poll_interval: str, max_lifetime: str):
    """Pins both settings (I3) tiny for the duration of the `with` block,
    reading them fresh via `get_settings()` the same way the handler is
    contracted to. Its own `MonkeyPatch.context()`, restored -- and the
    settings cache cleared again -- the moment the block exits, so a pinned
    value never survives into another scenario or another test file."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("SSE_POLL_INTERVAL_SECONDS", poll_interval)
        mp.setenv("SSE_MAX_LIFETIME_SECONDS", max_lifetime)
        get_settings.cache_clear()
        yield
    get_settings.cache_clear()


def _stream_path(run_id: str) -> str:
    return f"/api/v1/playthrough/campaign/{run_id}/stream"


def test_ac4_the_stream_announces_updates_and_ends_on_disconnect_or_lifetime(
    client, session_cookie_header, assert_error_envelope
):
    # <- AC4
    cookie = session_cookie_header("a-valid-cookie")

    # -- Member-gated before the stream opens: a refusal is the ordinary
    # error envelope, not a stream that opens and dies. `latest_event_id`
    # (I3's own per-tick seam) is the one place membership can be gated
    # from, so raising through it here proves the gate without a database.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)
        refused_run_id = generate_id()

        async def refusing_latest_event_id(db, **kwargs):
            raise CampaignRunNotFoundError(refused_run_id)

        mp.setattr(playthrough_service, "latest_event_id", refusing_latest_event_id)

        response = client.get(_stream_path(refused_run_id), headers=cookie)
        assert_error_envelope(response, status=404, code="NOT_FOUND")
        assert "text/event-stream" not in response.headers.get("content-type", "")

    # -- Content type, the `updated` message, the keepalive comment, and the
    # generator ending by itself once its bounded lifetime runs out.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)
        run_id = generate_id()
        old_id = generate_id()
        new_id = generate_id()
        sequence = [old_id, old_id, new_id, new_id]
        calls = {"n": 0}

        async def sequenced_latest_event_id(db, **kwargs):
            index = min(calls["n"], len(sequence) - 1)
            calls["n"] += 1
            return sequence[index]

        mp.setattr(playthrough_service, "latest_event_id", sequenced_latest_event_id)

        with _pinned_sse_settings(poll_interval="0.02", max_lifetime="0.3"):
            started = time.monotonic()
            with client.stream("GET", _stream_path(run_id), headers=cookie) as response:
                assert response.status_code == 200, response.read()
                assert response.headers["content-type"].startswith("text/event-stream")
                body = response.read().decode()
            elapsed = time.monotonic() - started

        expected_update = (
            "data: " + json.dumps({"type": "updated", "id": new_id}, separators=(",", ":")) + "\n\n"
        )
        assert expected_update in body
        assert ": keepalive\n\n" in body
        # Ended on its own once the pinned lifetime elapsed -- not
        # instantly, and nowhere near the unpinned 300s default.
        assert 0.2 <= elapsed <= 5.0

    # -- The generator ends when the listener goes away, proven through the
    # exact hook I3 names ("the loop ends on `await request.is_disconnected
    # ()`") rather than by fishing a bare generator out of routes.py's own
    # internals (module docstring). A lifetime pinned far larger than the
    # two polls this takes makes the distinction observable: had disconnect
    # not ended it, this would have run for the full pinned lifetime.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)
        disconnect_run_id = generate_id()
        steady_id = generate_id()

        async def steady_latest_event_id(db, **kwargs):
            return steady_id

        mp.setattr(playthrough_service, "latest_event_id", steady_latest_event_id)

        disconnect_calls = {"n": 0}

        async def fake_is_disconnected(self):
            disconnect_calls["n"] += 1
            return disconnect_calls["n"] >= 2

        mp.setattr(Request, "is_disconnected", fake_is_disconnected)

        with _pinned_sse_settings(poll_interval="0.02", max_lifetime="5.0"):
            started = time.monotonic()
            with client.stream("GET", _stream_path(disconnect_run_id), headers=cookie) as response:
                assert response.status_code == 200, response.read()
                response.read()
            elapsed = time.monotonic() - started

        assert disconnect_calls["n"] >= 2
        # Ended within a couple of poll intervals, nowhere near the 5s
        # lifetime pinned for this scenario -- disconnect, not the
        # lifetime bound, is what ended it.
        assert elapsed < 2.0


def _walk_routes(routes):
    """Every leaf route reachable from `routes`, descending into
    `_IncludedRouter` wrappers (this FastAPI/Starlette pin's own shape for
    an included router, `fastapi==0.141.1`) until a real `APIRoute` with a
    `path` turns up. Pure runtime introspection of FastAPI's own routing
    objects -- never a read of `routes.py` itself."""
    for route in routes:
        if type(route).__name__ == "_IncludedRouter":
            yield from _walk_routes(route.original_router.routes)
        else:
            yield route


def _find_stream_route(app):
    for route in _walk_routes(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None) or set()
        if path and path.endswith("/campaign/{run_id}/stream") and "GET" in methods:
            return route
    raise AssertionError("no GET .../campaign/{run_id}/stream route is registered")


def _call_stream_endpoint(route, *, run_id: str, request, auth: AuthContext, db: AsyncSession):
    """Calls the stream route's own function directly, matching its
    parameters by their declared *type* rather than by a guessed name, so
    this never depends on having read `routes.py`. This is what lets the
    `StreamingResponse` it returns -- and the generator inside it -- be
    driven by hand: `TestClient` fully buffers a streaming response before
    ever returning control (module docstring), so it cannot be used to
    observe a real insert arriving *while* the stream is open."""
    endpoint = route.endpoint
    hints = get_type_hints(endpoint, include_extras=True)
    kwargs = {}
    for name, param in inspect.signature(endpoint).parameters.items():
        annotation = hints.get(name, param.annotation)
        if get_origin(annotation) is Annotated:
            annotation = get_args(annotation)[0]
        if annotation is Request:
            kwargs[name] = request
        elif annotation is AuthContext:
            kwargs[name] = auth
        elif annotation is AsyncSession:
            kwargs[name] = db
        elif annotation is str:
            kwargs[name] = run_id
        else:
            raise AssertionError(f"unexpected stream endpoint parameter {name!r}: {annotation!r}")
    return endpoint(**kwargs)


class _NeverDisconnects:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.database
def test_ac4_the_real_signal_read_announces_a_committed_entry_and_gates_a_stranger(
    playthrough_db, session_cookie_header, assert_error_envelope
):
    # <- AC4 (the real query and the real membership gate -- no stub on
    # `latest_event_id` anywhere in this test)
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac4-real-owner")
        await _insert_user(playthrough_db, stranger_id, username="ac4-real-stranger")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )
        await playthrough_db.commit()
        # Captured now, as a plain string: the stream rolls back per poll
        # (I3), which expires every object this session ever loaded --
        # `run` must never be touched again after the stream below runs.
        run_id = run.id

        auth = AuthContext(
            user=SimpleNamespace(id=owner_id), session=SimpleNamespace(csrf_token="irrelevant")
        )

        with _pinned_sse_settings(poll_interval="0.02", max_lifetime="5.0"):
            route = _find_stream_route(create_app())
            streaming_response = await _call_stream_endpoint(
                route,
                run_id=run_id,
                request=_NeverDisconnects(),
                auth=auth,
                db=playthrough_db,
            )
            assert streaming_response.media_type == "text/event-stream"
            body_iterator = streaming_response.body_iterator
            try:
                # The baseline tick, before anything new exists.
                await body_iterator.__anext__()

                # A real transcript entry, written through the module's own
                # writer and committed on a separate connection while the
                # stream sits open -- `append_event` flushes without
                # committing (05a), so only this explicit commit, from a
                # connection distinct from the one the open stream polls
                # through, can make the entry visible to it.
                writer_engine = create_async_engine(os.environ["DATABASE_URL"])
                writer_sessionmaker = async_sessionmaker(writer_engine, expire_on_commit=False)
                try:
                    async with writer_sessionmaker() as writer_session:
                        new_event = await playthrough_service.append_event(
                            writer_session,
                            run_id=run_id,
                            type="narration",
                            visibility="player",
                            payload={"text": "a real entry, written elsewhere"},
                        )
                        await writer_session.commit()
                    new_event_id = new_event.id
                finally:
                    await writer_engine.dispose()

                expected_update = (
                    "data: "
                    + json.dumps({"type": "updated", "id": new_event_id}, separators=(",", ":"))
                    + "\n\n"
                )

                # Bounded attempts, not a wall-clock wait -- a miss here
                # must fail the test, never skip it.
                seen = None
                for _ in range(50):
                    chunk = await body_iterator.__anext__()
                    if chunk == expected_update:
                        seen = chunk
                        break
                assert seen is not None, (
                    "the stream never announced the committed entry through "
                    "the real latest_event_id query"
                )
            finally:
                await body_iterator.aclose()

        # The real membership gate (← D12), through the same function the
        # stream polls -- no stub in effect anywhere in this test.
        with pytest.raises(Exception) as exc_info:
            await playthrough_service.latest_event_id(
                playthrough_db, user_id=stranger_id, run_id=run_id
            )
        assert exc_info.value.code == ErrorCode.NOT_FOUND

        return run_id, stranger_id

    run_id, stranger_id = asyncio.run(_scenario())

    # -- The same refusal, this time as the ordinary HTTP error envelope
    # rather than a stream that opens and dies: a fresh app, its own
    # `get_db_session` left untouched so it reaches the same real scratch
    # database (`playthrough_db`'s own `DATABASE_URL` pin), with only auth
    # stubbed -- membership itself is decided for real.
    real_db_client = TestClient(create_app())
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp, user_id=stranger_id)
        response = real_db_client.get(
            _stream_path(run_id), headers=session_cookie_header("a-valid-cookie")
        )

    assert_error_envelope(response, status=404, code="NOT_FOUND")
    assert "text/event-stream" not in response.headers.get("content-type", "")
