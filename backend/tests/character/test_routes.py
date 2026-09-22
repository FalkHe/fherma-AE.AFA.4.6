"""AC1-AC5 -- sprint 009-05 "the creation conversation over the network"
(`docs/intents/009-character-creation/sprints/05-creation-chat-api/brief.md`).

One test per acceptance criterion, driven through `TestClient` against the
real routes with the sprint's own fixtures (`tests/character/conftest.py`):
`signed_in`, `run_overview`, `scripted_model`. AC6 (the regenerated client)
has no test of its own -- WI2 and `make backend-lint` cover it.
"""

from app.core.ids import generate_id
from app.modules.playthrough import service as playthrough_service


def _start(client, signed_in, run_id: str):
    return client.post(f"/api/v1/character/runs/{run_id}/creation", headers=signed_in.headers)


def _send(client, signed_in, conversation_id: str, text: str):
    return client.post(
        f"/api/v1/character/creation/{conversation_id}/messages",
        json={"text": text},
        headers=signed_in.headers,
    )


def test_ac1_starting_greets_and_a_run_with_a_character_is_refused(client, signed_in, run_overview):
    run_id = generate_id()
    run_overview(run_id)

    response = _start(client, signed_in, run_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert "Rosalind Thorn" in body["reply"]
    assert body["step"] == "raceClass"

    taken_run_id = generate_id()
    run_overview(taken_run_id, has_character=True)

    refused = _start(client, signed_in, taken_run_id)

    assert refused.status_code == 409, refused.text
    assert refused.json() == {
        "error": {
            "code": "CHARACTER_EXISTS",
            "message": "This campaign run already has a character.",
            "details": None,
        }
    }


def test_ac2_one_message_yields_exactly_the_scripted_reply(
    client, signed_in, run_overview, scripted_model
):
    run_id = generate_id()
    run_overview(run_id)
    scripted_model("A halfling rogue, then -- light feet and lighter fingers.")

    started = _start(client, signed_in, run_id)
    conversation_id = started.json()["conversationId"]

    response = _send(client, signed_in, conversation_id, "a sneaky halfling burglar")

    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "A halfling rogue, then -- light feet and lighter fingers."


def test_ac3_every_reply_carries_the_sheet_step_and_can_save(
    client, signed_in, run_overview, scripted_model
):
    run_id = generate_id()
    run_overview(run_id)
    # One conversation, two player messages: the first settles race/class
    # only, the second finishes every remaining step.
    scripted_model(
        ("set_race_and_class", {"race": "Halfling", "character_class": "Rogue"}),
        "A halfling rogue, then -- written down.",
        ("set_identity", {"name": "Pip"}),
        ("suggest_scores", {}),
        ("set_skills", {"first": "Stealth", "second": "Deception"}),
        ("set_alignment", {"alignment": "Chaotic Good"}),
        ("take_default_equipment", {}),
        "Written down, top to bottom.",
    )

    started = _start(client, signed_in, run_id)
    conversation_id = started.json()["conversationId"]

    partial = _send(client, signed_in, conversation_id, "a halfling rogue")

    assert partial.status_code == 200, partial.text
    body = partial.json()
    assert body["sheet"]["race"] == "Halfling"
    assert body["sheet"]["characterClass"] == "Rogue"
    assert body["step"] == "scores"
    assert body["canSave"] is False

    complete = _send(client, signed_in, conversation_id, "named Pip, chaotic good, default gear")

    assert complete.status_code == 200, complete.text
    complete_body = complete.json()
    assert complete_body["step"] == "review"
    assert complete_body["canSave"] is True
    assert complete_body["sheet"]["maxHp"] is not None


def test_ac4_anonymous_unknown_conversation_and_model_failure_are_refused_in_voice(
    client, signed_in, run_overview, scripted_model
):
    run_id = generate_id()
    run_overview(run_id)

    anonymous = client.post(f"/api/v1/character/runs/{run_id}/creation")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "NOT_AUTHENTICATED"

    unknown_conversation = _send(client, signed_in, "no-such-conversation", "hello?")
    assert unknown_conversation.status_code == 404
    assert unknown_conversation.json()["error"]["code"] == "NOT_FOUND"

    scripted_model(RuntimeError("the model fell over"))
    started = _start(client, signed_in, run_id)
    conversation_id = started.json()["conversationId"]

    failed = _send(client, signed_in, conversation_id, "keep going")

    assert failed.status_code == 200, failed.text
    body = failed.json()
    assert body["error"] is True
    assert body["reply"] == "The tavern is noisy, I did not catch that. Say it again?"


def test_ac5_an_unfinished_conversation_never_calls_create_character(
    client, signed_in, run_overview, scripted_model, monkeypatch
):
    calls = []

    async def fake_create_character(db, **kwargs):
        calls.append(kwargs)
        return None

    monkeypatch.setattr(playthrough_service, "create_character", fake_create_character)

    run_id = generate_id()
    run_overview(run_id)
    scripted_model("Well met. Tell me who you'd rather be.")

    started = _start(client, signed_in, run_id)
    conversation_id = started.json()["conversationId"]
    _send(client, signed_in, conversation_id, "a sneaky halfling burglar")

    assert calls == []
