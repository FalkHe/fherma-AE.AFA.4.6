"""qa acceptance tests -- sprint 005/05a "the transcript records and reads
back"
(`docs/intents/005-game-state-services/sprints/05a-transcript-writer-and-read/brief.md`).

Black-box throughout, against the sprint's own interface contracts
(`plan.md -> Interfaces`), never against `app.modules.playthrough.service`,
`.routes`, `.schemas` or `.errors` themselves -- those are this sprint's own
work items, written in parallel, and this file never reads them.

AC1 needs no database: `append_event`'s own contract is "add + flush so the
id exists, no commit" -- nothing more is ever asked of `db` -- so a
duck-typed recording stand-in exercises the twelve-kind validation and the
"nothing written on refusal" promise without a real connection. Whether it
is really the *only* writer is a structural question no schema constraint
can answer, so that part is a static `ast` scan of the whole backend tree,
exactly as the sprint's own research names it.

AC2 carries `@pytest.mark.database`: its wire half (which five keys an
event reads as, `after`/`limit` reaching the service, the `limit` cap, the
member-gated 404) is exercised through `client` with a stubbed session and
a monkeypatched `list_events`, scoped to its own `MonkeyPatch.context()` so
nothing leaks into the real-database half that follows -- ordering,
`after`-exclusive paging, `limit`, and the DM entry that is missing from
the read but still in the table -- which drives `append_event` /
`list_events` directly against the shared scratch database
(`playthrough_db`). Mixing `TestClient` and a real `AsyncSession` in one
test is a documented hazard in this suite (`test_acceptance_adventure_progress
.py`), which is why the two halves never touch the same session and the
database half never goes through `TestClient`.

AC5 reads the shipped module documentation directly -- no code, no mocks --
both `docs/modules/playthrough.md` (mounted read-only into the test
container at `/docs`, per `compose.yaml`) and the in-tree module
`README.md`, matched on whitespace-normalised substrings so a prose reflow
in either document can never break this on wording the criterion does not
actually depend on.

No `pytest-asyncio` in this suite (`AGENTS.md` gotchas); every async call in
the database-backed scenario is wrapped in a single `asyncio.run(...)`.

Written against the sprint's interface contracts, not against the service,
routes, schemas or docs themselves -- this suite is red until the
corresponding work items land, and green once they do.
"""

import ast
import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.errors import ApiError, ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.playthrough import service as playthrough_service
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
APP_ROOT = BACKEND_ROOT / "app"

USER_ID = generate_id()
CSRF_TOKEN = "the-matching-csrf-token"  # noqa: S105 - fixture value, not a secret

RUN_ID = generate_id()
ACTOR_ID = generate_id()
ADVENTURE_RUN_ID = generate_id()

# The twelve kinds and the shape each one promises (`decisions/mechanics.md`
# "Shapes carried in `events.payload`"; `narration`/`system`/`error`/`warning`
# from `research.md` "Open questions"), written camelCase -- `payload` is
# stored camelCase and read back unchanged.
VALID_PAYLOADS: dict[str, dict] = {
    "narration": {"text": "The tavern falls silent as you enter."},
    "player_action": {"text": "I search the room for traps."},
    "roll_requested": {
        "kind": "attack",
        "actorId": ACTOR_ID,
        "formula": "1d20+3",
        "context": {"targetAc": 14},
    },
    "roll": {
        "kind": "attack",
        "actorId": ACTOR_ID,
        "formula": "1d20+3",
        "faces": [17],
        "modifier": 3,
        "total": 20,
    },
    "question": {"text": "Which door do you take?", "options": ["left", "right"]},
    "tool_call": {
        "name": "lookup_rule",
        "args": {"query": "grapple"},
        "rollIds": [],
        "result": "ok",
        "outcome": {"summary": "found the rule"},
    },
    "scene_entered": {"adventureRunId": ADVENTURE_RUN_ID, "sceneId": "scene-1"},
    "adventure_started": {"adventureRunId": ADVENTURE_RUN_ID},
    "adventure_completed": {"adventureRunId": ADVENTURE_RUN_ID},
    "system": {"message": "Autosaved."},
    "error": {"message": "The dice roller is unavailable."},
    "warning": {"message": "You are low on spell slots."},
}

# Each one is the matching valid payload with the field its shape requires
# removed (or, for `tool_call`, a value outside its declared `ok | refused`
# result) -- the minimal way each shape can fail to match what its kind
# promises.
INVALID_PAYLOADS: dict[str, dict] = {
    "narration": {},
    "player_action": {},
    "roll_requested": {"kind": "attack", "actorId": ACTOR_ID, "context": {"targetAc": 14}},
    "roll": {"kind": "attack", "actorId": ACTOR_ID, "formula": "1d20+3", "faces": [17]},
    "question": {"text": "Which door do you take?"},
    "tool_call": {**VALID_PAYLOADS["tool_call"], "result": "maybe"},
    "scene_entered": {"adventureRunId": ADVENTURE_RUN_ID},
    "adventure_started": {},
    "adventure_completed": {},
    "system": {},
    "error": {},
    "warning": {},
}


def _stub_auth(monkeypatch, *, user_id: str = USER_ID, csrf_token: str = CSRF_TOKEN):
    session = make_session(user_id=user_id, csrf_token=csrf_token)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


async def _insert_user(session, user_id: str, *, username: str) -> None:
    await session.execute(
        text("INSERT INTO users (id, username, password_hash) VALUES (:id, :username, 'x')"),
        {"id": user_id, "username": username},
    )


class _RecordingSession:
    """A duck-typed stand-in for the `AsyncSession` `append_event` is
    handed. The sprint's own interface contract asks nothing of `db` beyond
    `add` (sync) and `flush` (async) -- "add + flush so the id exists, no
    commit" -- so this records every added row without needing a real
    database for what is, at its core, a pure validation question: does
    this payload match the shape its kind promises."""

    def __init__(self) -> None:
        self.added: list = []

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


class _EventConstructorVisitor(ast.NodeVisitor):
    """Records, for every `Event(...)` construction found anywhere in the
    backend tree, the name of the function (if any) enclosing it. Matches
    both construction forms: a bare `Event(...)` (`ast.Name`) and
    `<module>.Event(...)` (`ast.Attribute`) -- the latter is the form
    `AGENTS.md` prescribes for reaching another module's internals ("only
    its `service.py` / `models.py`"), so it is exactly the shape a future
    sprint's mechanic would write when it calls `models.Event(...)`
    directly instead of going through `append_event`."""

    def __init__(self) -> None:
        self.call_sites: list[str] = []
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
            self.call_sites.append(self._function_stack[-1] if self._function_stack else "<module>")
        self.generic_visit(node)


def _event_call_sites_in_source(source: str) -> list[str]:
    """Every enclosing-function name the visitor records for `source`
    (`"<module>"` for a call at top level) -- exercises the visitor itself
    against a small string, so the tree-wide scan below is never trusted to
    have been the only thing that ever ran the failure path."""
    visitor = _EventConstructorVisitor()
    visitor.visit(ast.parse(source))
    return visitor.call_sites


def _event_constructor_call_sites() -> set[str]:
    sites: set[str] = set()
    for path in sorted(APP_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        visitor = _EventConstructorVisitor()
        visitor.visit(tree)
        relative = path.relative_to(APP_ROOT.parent)
        sites.update(f"{relative}:{fn}" for fn in visitor.call_sites)
    return sites


def test_ac1_every_kind_validates_its_own_shape_and_only_one_function_writes():
    # <- AC1
    async def _scenario():
        db = _RecordingSession()

        for kind, payload in VALID_PAYLOADS.items():
            event = await playthrough_service.append_event(
                db, run_id=RUN_ID, type=kind, visibility="player", payload=payload
            )
            assert db.added[-1] is event, kind
            assert event.type == kind
            assert event.visibility == "player"
            for key, value in payload.items():
                assert event.payload.get(key) == value, (kind, event.payload)

        assert len(db.added) == len(VALID_PAYLOADS)

        for kind, bad_payload in INVALID_PAYLOADS.items():
            written_before = len(db.added)
            with pytest.raises(Exception) as exc_info:
                await playthrough_service.append_event(
                    db, run_id=RUN_ID, type=kind, visibility="player", payload=bad_payload
                )
            assert exc_info.value.code == ErrorCode.VALIDATION_ERROR, kind
            assert len(db.added) == written_before, f"{kind} wrote a row despite refusal"

        # An unknown kind is refused the same way.
        written_before = len(db.added)
        with pytest.raises(Exception) as exc_info:
            await playthrough_service.append_event(
                db, run_id=RUN_ID, type="monologue", visibility="player", payload={"text": "x"}
            )
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert len(db.added) == written_before

        # An unknown visibility is refused the same way, even with an
        # otherwise-valid payload for a real kind.
        written_before = len(db.added)
        with pytest.raises(Exception) as exc_info:
            await playthrough_service.append_event(
                db, run_id=RUN_ID, type="narration", visibility="everyone", payload={"text": "x"}
            )
        assert exc_info.value.code == ErrorCode.VALIDATION_ERROR
        assert len(db.added) == written_before

    asyncio.run(_scenario())

    # The guard itself, on two small source strings, one per construction
    # form -- a guard nobody has watched fail is not a guard. Both the bare
    # name and the attribute form must be caught, and an unrelated call
    # sharing no name with `Event` must not be.
    assert _event_call_sites_in_source("def f():\n    Event(a=1)\n") == ["f"]
    assert _event_call_sites_in_source("def f():\n    models.Event(a=1)\n") == ["f"]
    assert _event_call_sites_in_source("def f():\n    EventFactory(a=1)\n") == []

    # Nothing in the schema stops a second module writing `events` directly
    # -- this is the only thing that would catch it, in either the bare or
    # the attribute-qualified form (`models.Event(...)`, the shape
    # `AGENTS.md` prescribes for reaching another module's internals).
    call_sites = _event_constructor_call_sites()
    assert call_sites == {"app/modules/playthrough/service.py:append_event"}, call_sites


@pytest.mark.database
def test_ac2_the_player_visible_transcript_orders_pages_and_hides_dm_entries(
    client, session_cookie_header, assert_error_envelope, playthrough_db
):
    # <- AC2
    wire_run_id = generate_id()

    # -- Wire contract: an event reads as exactly five camelCase keys, no
    # visibility and no cost even though the underlying row carries them;
    # `after`/`limit` reach the service; a `limit` past the cap is refused
    # before it does; an unknown-or-foreign run is `NOT_FOUND`. Scoped to
    # its own `MonkeyPatch.context()`, not the `monkeypatch` fixture, so
    # every patch here is undone before the real-database scenario below
    # runs the very same service functions for real.
    with pytest.MonkeyPatch.context() as mp:
        _stub_auth(mp)

        fake_events = [
            SimpleNamespace(
                id="01AAAAAAAAAAAAAAAAAAAAAAAA",
                type="narration",
                visibility="player",
                turn_id=None,
                payload={"text": "It begins."},
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
                campaign_run_id=wire_run_id,
                actor_member_id=None,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=Decimal("0.000100"),
            ),
            SimpleNamespace(
                id="01BBBBBBBBBBBBBBBBBBBBBBBB",
                type="roll",
                visibility="player",
                turn_id="01TURNTURNTURNTURNTURNTUR",
                payload={"total": 15},
                created_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
                campaign_run_id=wire_run_id,
                actor_member_id=None,
                prompt_tokens=None,
                completion_tokens=None,
                cost_usd=None,
            ),
        ]

        captured: dict = {}

        async def fake_list_events(db, **kwargs):
            captured.update(kwargs)
            return fake_events

        mp.setattr(playthrough_service, "list_events", fake_list_events)

        response = client.get(
            f"/api/v1/playthrough/campaign/{wire_run_id}/events",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == len(fake_events)
        for item, source in zip(body, fake_events, strict=True):
            assert set(item.keys()) == {"id", "type", "turnId", "payload", "createdAt"}, item
            assert item["id"] == str(source.id)
            assert item["type"] == source.type
            assert item["turnId"] == source.turn_id
            assert item["payload"] == source.payload

        assert captured.get("user_id") == USER_ID
        assert captured.get("run_id") == wire_run_id
        assert captured.get("after") is None
        assert captured.get("limit") == 200  # default, per the interface contract

        paged_captured: dict = {}

        async def fake_list_events_paged(db, **kwargs):
            paged_captured.update(kwargs)
            return []

        mp.setattr(playthrough_service, "list_events", fake_list_events_paged)
        after_id = generate_id()
        paged_response = client.get(
            f"/api/v1/playthrough/campaign/{wire_run_id}/events?after={after_id}&limit=5",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert paged_response.status_code == 200, paged_response.text
        assert paged_captured.get("after") == after_id
        assert paged_captured.get("limit") == 5

        over_cap_response = client.get(
            f"/api/v1/playthrough/campaign/{wire_run_id}/events?limit=501",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert_error_envelope(over_cap_response, status=422, code="VALIDATION_ERROR")

        async def fake_list_events_not_found(db, **kwargs):
            raise ApiError(ErrorCode.NOT_FOUND)

        mp.setattr(playthrough_service, "list_events", fake_list_events_not_found)
        missing_response = client.get(
            f"/api/v1/playthrough/campaign/{generate_id()}/events",
            headers=session_cookie_header("a-valid-cookie"),
        )
        assert_error_envelope(missing_response, status=404, code="NOT_FOUND")

    # -- Real database, no monkeypatch in effect: ordering by id alone,
    # `after`-exclusive paging, `limit`, a `dm` entry missing from every read
    # above while still present in the table, and membership gating -- all
    # driven directly against `append_event` / `list_events`, never through
    # `TestClient` (see the module docstring for why).
    async def _scenario():
        owner_id = generate_id()
        stranger_id = generate_id()
        await _insert_user(playthrough_db, owner_id, username="ac2-owner")
        await _insert_user(playthrough_db, stranger_id, username="ac2-stranger")
        await playthrough_db.commit()

        run = await playthrough_service.start_campaign_run(
            playthrough_db, user_id=owner_id, campaign_id="greenhollow"
        )

        p1 = await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="narration",
            visibility="player",
            payload={"text": "one"},
        )
        dm1 = await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="system",
            visibility="dm",
            payload={"message": "hidden from the player"},
        )
        p2 = await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="narration",
            visibility="player",
            payload={"text": "two"},
        )
        p3 = await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="narration",
            visibility="player",
            payload={"text": "three"},
        )
        p4 = await playthrough_service.append_event(
            playthrough_db,
            run_id=run.id,
            type="narration",
            visibility="player",
            payload={"text": "four"},
        )
        await playthrough_db.commit()

        full = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id
        )
        assert [e.id for e in full] == [p1.id, p2.id, p3.id, p4.id]

        after_p1 = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id, after=p1.id
        )
        assert [e.id for e in after_p1] == [p2.id, p3.id, p4.id]

        first_page = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id, after=p1.id, limit=1
        )
        assert [e.id for e in first_page] == [p2.id]

        second_page = await playthrough_service.list_events(
            playthrough_db, user_id=owner_id, run_id=run.id, after=p2.id, limit=1
        )
        assert [e.id for e in second_page] == [p3.id]

        # The dm entry is absent from every read above, and still in the
        # table.
        stored_dm = (
            await playthrough_db.execute(
                text("SELECT id, visibility FROM events WHERE id = :id"), {"id": dm1.id}
            )
        ).first()
        assert stored_dm is not None
        assert stored_dm.visibility == "dm"

        table_count = (
            await playthrough_db.execute(
                text("SELECT count(*) FROM events WHERE campaign_run_id = :id"), {"id": run.id}
            )
        ).scalar_one()
        assert table_count == 5

        # Member-gated: an unknown run and a run belonging to someone else
        # both answer `NOT_FOUND`.
        with pytest.raises(Exception) as unknown_exc:
            await playthrough_service.list_events(
                playthrough_db, user_id=owner_id, run_id=generate_id()
            )
        assert unknown_exc.value.code == ErrorCode.NOT_FOUND

        with pytest.raises(Exception) as foreign_exc:
            await playthrough_service.list_events(
                playthrough_db, user_id=stranger_id, run_id=run.id
            )
        assert foreign_exc.value.code == ErrorCode.NOT_FOUND

    asyncio.run(_scenario())


DOC_PATH = REPO_ROOT / "docs" / "modules" / "playthrough.md"
README_PATH = APP_ROOT / "modules" / "playthrough" / "README.md"


def _assert_states_the_id_ordering_caveat(content: str, *, source: Path) -> None:
    """The three ideas AC5 asks for -- matched as independent substrings
    against whitespace-normalised text (`docs/modules/playthrough.md` and
    the module `README.md` wrap their prose at different widths, so a
    literal multi-word phrase can straddle a line break in one document and
    not the other) -- never a whole sentence, so either document's wording
    can still be edited without this test caring."""
    normalized = " ".join(content.split())

    # The transcript's order comes from the entry ids.
    assert "by `id`" in normalized, source

    # That holds only because a single process mints every one of them.
    assert "one process" in normalized, source
    assert "mints" in normalized, source

    # It would break the moment the app ran as more than one process.
    assert "second process" in normalized or "two different processes" in normalized, source


def test_ac5_the_module_doc_and_readme_state_the_id_ordering_caveat():
    # <- AC5
    assert DOC_PATH.exists(), (
        f"expected {DOC_PATH} to exist -- docs/ is mounted read-only into "
        "the test container at /docs (compose.yaml)"
    )
    _assert_states_the_id_ordering_caveat(DOC_PATH.read_text(), source=DOC_PATH)

    assert README_PATH.exists(), f"expected {README_PATH} to exist"
    _assert_states_the_id_ordering_caveat(README_PATH.read_text(), source=README_PATH)
