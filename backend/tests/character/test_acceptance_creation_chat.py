"""qa acceptance tests -- sprint 009-05 "the creation conversation over the
network"
(`docs/intents/009-character-creation/sprints/05-creation-chat-api/brief.md`).

Black-box over the wire only (`TestClient`, DB session stubbed): this file
never imports `app.modules.character.routes` or `.service` and asserts
nothing about their internals. Auth/CSRF and run membership are set up
through the sprint's own fixtures (`tests/character/conftest.py`):
`signed_in`, `run_overview` and `scripted_model`. One test per criterion
this sprint assigns to qa (AC1, AC2, AC4; AC3/AC5/AC6 are WI1's own tests
per `plan.md`).

Written against the sprint's interface contract, not against the routes or
schemas themselves -- this suite is red until `feat(character): creation
chat routes and scripted model fixture` lands, and green once it does.
"""

from app.core.ids import generate_id


def _start(client, signed_in, run_id: str):
    return client.post(
        f"/api/v1/character/runs/{run_id}/creation",
        headers=signed_in.headers,
    )


def test_ac1_start_greets_with_the_ready_made_hero_and_refuses_a_run_with_a_character(
    client, signed_in, run_overview
):
    # <- AC1
    run_id = generate_id()
    run_overview(run_id)

    response = _start(client, signed_in, run_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert "Rosalind Thorn" in body["reply"]
    assert body["step"] == "raceClass"

    existing_run_id = generate_id()
    run_overview(existing_run_id, has_character=True)

    refused = _start(client, signed_in, existing_run_id)

    assert refused.status_code == 409, refused.text
    error = refused.json()["error"]
    assert error["code"] == "CHARACTER_EXISTS"


def test_ac2_one_message_yields_one_whole_reply(client, signed_in, run_overview, scripted_model):
    # <- AC2
    run_id = generate_id()
    run_overview(run_id)
    scripted_model("Welcome, traveller. What is your name?")

    started = _start(client, signed_in, run_id)
    assert started.status_code == 201, started.text
    conversation_id = started.json()["conversationId"]

    response = client.post(
        f"/api/v1/character/creation/{conversation_id}/messages",
        json={"text": "I am ready to begin."},
        headers=signed_in.headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] == "Welcome, traveller. What is your name?"
    assert body["saved"] is False


def test_ac4_refusals_and_model_failure_stay_in_the_envelope_or_in_voice(
    client, signed_in, run_overview, scripted_model
):
    # <- AC4
    run_id = generate_id()
    run_overview(run_id)

    anonymous_response = client.post(f"/api/v1/character/runs/{run_id}/creation")
    assert anonymous_response.status_code == 401, anonymous_response.text
    assert anonymous_response.json()["error"]["code"] == "NOT_AUTHENTICATED"

    unknown_conversation_response = client.post(
        "/api/v1/character/creation/no-such-conversation/messages",
        json={"text": "Hello?"},
        headers=signed_in.headers,
    )
    assert unknown_conversation_response.status_code == 404, unknown_conversation_response.text
    assert unknown_conversation_response.json()["error"]["code"] == "NOT_FOUND"

    scripted_model(RuntimeError("boom"))
    started = _start(client, signed_in, run_id)
    assert started.status_code == 201, started.text
    conversation_id = started.json()["conversationId"]

    failed_response = client.post(
        f"/api/v1/character/creation/{conversation_id}/messages",
        json={"text": "Let's continue."},
        headers=signed_in.headers,
    )

    assert failed_response.status_code == 200, failed_response.text
    body = failed_response.json()
    assert body["error"] is True
    assert body["reply"]
    assert "Traceback" not in body["reply"]
    assert "boom" not in body["reply"]
