"""qa acceptance tests -- sprint 010/03 "a turn can be taken over the
network" (`docs/intents/010-dm-agent-in-gui/sprints/03-turn-endpoint/brief.md`,
AC1-AC6).

Black-box through the network call only, exactly as `plan.md`'s "Acceptance
tests (qa)" section prescribes: `POST /api/v1/game/runs/{runId}/turn` is
driven with `TestClient`, and `app.modules.game.service.run_turn` (I2) is
monkeypatched wholesale rather than any of its own internals -- this file
never reads `game/service.py`, `game/agent/*` or the route module WI1/WI2
are writing in parallel. `raising=False` on every `monkeypatch.setattr` of
`run_turn` because it may not exist yet while those work items are still
in flight (same seam and reasoning as
`tests/core/llm/test_commands_image.py`).

Auth and CSRF are stubbed exactly as `tests/playthrough/test_routes.py`
stubs them for its own module's routes: `auth_service.resolve_session` and
`users_service.get_user_by_id` monkeypatched, never a real session or a
real database.

Every test asserts the fake `run_turn` was actually invoked before
asserting anything about the HTTP response. Without that guard, a route
that simply does not exist yet answers a plain FastAPI 404 that this
suite's own error-envelope handler already turns into the same
`{"error": {"code": "NOT_FOUND", ...}}` shape AC6 itself expects -- which
would make AC6 pass for the wrong reason (the endpoint being entirely
absent) rather than for the reason the brief names (the caller not being
seated at the run). Asserting the call landed rules that out.
"""

from dataclasses import dataclass

from app.core.errors import ErrorCode
from app.core.ids import generate_id
from app.modules.auth import service as auth_service
from app.modules.game import service as game_service
from app.modules.playthrough.errors import CampaignRunNotFoundError, PlaythroughError
from app.modules.users import service as users_service
from tests.factories import make_session, make_user

USER_ID = generate_id()
RUN_ID = generate_id()
CSRF_TOKEN = "the-matching-csrf-token"  # noqa: S105 - fixture value, not a secret


def _stub_auth(monkeypatch, *, user_id: str = USER_ID, csrf_token: str = CSRF_TOKEN):
    session = make_session(user_id=user_id, csrf_token=csrf_token)
    user = make_user(user_id=user_id)

    async def fake_resolve_session(db, *, token):
        return session

    async def fake_get_user_by_id(db, *, user_id):
        return user

    monkeypatch.setattr(auth_service, "resolve_session", fake_resolve_session)
    monkeypatch.setattr(users_service, "get_user_by_id", fake_get_user_by_id)


def _auth_headers(session_cookie_header, *, csrf_token: str = CSRF_TOKEN):
    return {**session_cookie_header("a-valid-cookie"), "X-CSRF-Token": csrf_token}


def _turn_url(run_id: str = RUN_ID) -> str:
    return f"/api/v1/game/runs/{run_id}/turn"


@dataclass(frozen=True)
class _Outcome:
    """Duck-typed stand-in for I2's `TurnOutcome`."""

    turn_id: str
    kind: str
    awaiting: str


class _FakeActionNotAvailable(PlaythroughError):
    """A local stand-in for whatever exception WI1 raises for AC2's
    refusal -- real `PlaythroughError` subclass (so any `except
    PlaythroughError` in the real route catches it regardless of the name
    WI1 eventually gives it), carrying `.details` the way I2 promises."""

    code = ErrorCode.ACTION_NOT_AVAILABLE

    def __init__(self, *, awaiting: str, options: list[str]) -> None:
        self.details = {"awaiting": awaiting, "options": options}
        super().__init__("action not available")


def _install_run_turn(
    monkeypatch, *, outcome: _Outcome | None = None, error: Exception | None = None
):
    """Patches `game_service.run_turn` to record every call it receives and
    either return `outcome` or raise `error`. Returns the `calls` list."""
    calls = []

    async def fake_run_turn(db, *, user_id, run_id, text):
        calls.append({"user_id": user_id, "run_id": run_id, "text": text})
        if error is not None:
            raise error
        return outcome

    monkeypatch.setattr(game_service, "run_turn", fake_run_turn, raising=False)
    return calls


def test_ac1_free_words_on_a_run_awaiting_nothing_reach_the_service_and_answer_names_what_is_next(
    client, monkeypatch, session_cookie_header
):
    """← AC1"""
    _stub_auth(monkeypatch)
    outcome = _Outcome(turn_id=generate_id(), kind="action", awaiting="roll:evt-42")
    calls = _install_run_turn(monkeypatch, outcome=outcome)

    response = client.post(
        _turn_url(),
        json={"text": "I search the abandoned well."},
        headers=_auth_headers(session_cookie_header),
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    assert calls[0] == {
        "user_id": USER_ID,
        "run_id": RUN_ID,
        "text": "I search the abandoned well.",
    }

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"turnId", "kind", "awaiting"}
    assert body["turnId"] == outcome.turn_id
    assert body["kind"] == "action"
    assert body["awaiting"] == "roll:evt-42"


def test_ac2_an_offered_choice_continues_the_turn_an_off_menu_answer_is_refused(
    client, monkeypatch, session_cookie_header
):
    """← AC2"""
    _stub_auth(monkeypatch)

    # Part 1: the offered choice continues the turn.
    outcome = _Outcome(turn_id="turn-open-1", kind="answer", awaiting="none")
    calls = _install_run_turn(monkeypatch, outcome=outcome)

    ok_response = client.post(
        _turn_url(),
        json={"text": "Take the left path"},
        headers=_auth_headers(session_cookie_header),
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    assert ok_response.status_code == 200, ok_response.text
    ok_body = ok_response.json()
    assert ok_body["kind"] == "answer"
    assert ok_body["turnId"] == "turn-open-1"
    assert ok_body["awaiting"] == "none"

    # Part 2: free words that are not one of the offered options are refused,
    # naming what is awaited.
    refusal = _FakeActionNotAvailable(
        awaiting="answer:evt-7", options=["Take the left path", "Take the right path"]
    )
    calls = _install_run_turn(monkeypatch, error=refusal)

    refused_response = client.post(
        _turn_url(),
        json={"text": "I set the whole village on fire instead"},
        headers=_auth_headers(session_cookie_header),
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    assert refused_response.status_code == 409, refused_response.text
    refused_body = refused_response.json()
    error = refused_body["error"]
    assert error["code"] == "ACTION_NOT_AVAILABLE"
    assert error["details"] == {
        "awaiting": "answer:evt-7",
        "options": ["Take the left path", "Take the right path"],
    }


def test_ac3_a_requested_roll_is_the_servers_and_a_caller_sent_number_is_ignored(
    client, monkeypatch, session_cookie_header
):
    """← AC3"""
    _stub_auth(monkeypatch)
    outcome = _Outcome(turn_id="turn-open-2", kind="roll", awaiting="none")
    calls = _install_run_turn(monkeypatch, outcome=outcome)

    first = client.post(
        _turn_url(), json={"text": "5"}, headers=_auth_headers(session_cookie_header)
    )
    second = client.post(
        _turn_url(), json={"text": "97"}, headers=_auth_headers(session_cookie_header)
    )

    assert len(calls) == 2, "the request never reached the turn engine"
    assert [c["text"] for c in calls] == ["5", "97"]

    # Whichever number the caller sent, the server's own decision (kind, the
    # turn resumed, what is awaited next) is identical -- the response never
    # varies with, or echoes, the caller's number.
    for response in (first, second):
        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body.keys()) == {"turnId", "kind", "awaiting"}
        assert body["kind"] == "roll"
        assert body["turnId"] == "turn-open-2"
        assert body["awaiting"] == "none"


def test_ac4_a_retry_resumes_the_broken_turn_without_repeating_the_roll(
    client, monkeypatch, session_cookie_header
):
    """← AC4"""
    _stub_auth(monkeypatch)
    broken_turn_id = "turn-that-broke-after-a-roll"
    outcome = _Outcome(turn_id=broken_turn_id, kind="retry", awaiting="none")
    calls = _install_run_turn(monkeypatch, outcome=outcome)

    response = client.post(
        _turn_url(), json={"text": None}, headers=_auth_headers(session_cookie_header)
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    assert calls[0]["text"] is None

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "retry"
    # The resumed leg reuses the broken turn's own id -- it is not a new turn.
    assert body["turnId"] == broken_turn_id
    assert body["awaiting"] == "none"


def test_ac5_an_opening_turn_with_no_text_carries_no_player_words(
    client, monkeypatch, session_cookie_header
):
    """← AC5"""
    _stub_auth(monkeypatch)
    outcome = _Outcome(turn_id=generate_id(), kind="opening", awaiting="none")
    calls = _install_run_turn(monkeypatch, outcome=outcome)

    response = client.post(
        _turn_url(), json={"text": None}, headers=_auth_headers(session_cookie_header)
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    # No player words at all reached the service -- an opening turn writes no
    # player row.
    assert calls[0]["text"] is None

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == "opening"
    assert body["turnId"] == outcome.turn_id
    assert body["awaiting"] == "none"


def test_ac6_a_run_the_caller_is_not_seated_at_refuses_any_turn(
    client, monkeypatch, session_cookie_header, assert_error_envelope
):
    """← AC6"""
    _stub_auth(monkeypatch)
    calls = _install_run_turn(monkeypatch, error=CampaignRunNotFoundError(RUN_ID))

    response = client.post(
        _turn_url(), json={"text": "anything at all"}, headers=_auth_headers(session_cookie_header)
    )

    assert len(calls) == 1, "the request never reached the turn engine"
    assert_error_envelope(response, status=404, code="NOT_FOUND")
