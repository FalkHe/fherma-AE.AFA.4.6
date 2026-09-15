"""qa acceptance test — sprint 001/02 AC6: an `LlmError` raised inside a
route surfaces through the existing `ErrorCode` / `ApiError` envelope
(`app/core/errors.py`), with its own code and the one shared message.

No route in this codebase calls the LLM seam yet (research.md: "no route
calls the seam, nor is one in scope"), so this test adds one throwaway
route to a fresh `app` fixture instance (`tests/conftest.py`) and asserts
what the already-registered `@app.exception_handler(LlmError)`
(`register_error_handlers`, `app/core/errors.py`) does with it -- the
behaviour under test is the handler dispatching on `exc.code`, not the
route itself.
"""

from fastapi.testclient import TestClient

from app.core.llm.errors import LlmAuthError, LlmRateLimitError


def test_ac6_llm_error_reaches_the_wire_through_the_standard_envelope(app, assert_error_envelope):
    # ← AC6
    @app.get("/__test/llm-error-auth")
    def _raise_llm_auth_error():
        raise LlmAuthError("invalid api key")

    client = TestClient(app)
    response = client.get("/__test/llm-error-auth")

    error = assert_error_envelope(response, status=502, code="LLM_AUTH")
    assert error["message"] == "The AI service could not complete that request."
    assert error["details"] is None


def test_ac6_a_different_llm_error_class_carries_its_own_code_and_the_same_message(
    app, assert_error_envelope
):
    # ← AC6 -- proves the handler dispatches per `exc.code`, not a single
    # hard-coded value, while the message text stays identical (D2).
    @app.get("/__test/llm-error-rate-limit")
    def _raise_llm_rate_limit_error():
        raise LlmRateLimitError("slow down")

    client = TestClient(app)
    response = client.get("/__test/llm-error-rate-limit")

    error = assert_error_envelope(response, status=502, code="LLM_RATE_LIMIT")
    assert error["message"] == "The AI service could not complete that request."


def test_ac6_llm_error_provider_message_never_reaches_the_wire(app, assert_error_envelope):
    # ← AC6 -- the envelope carries only the shared message; the provider's
    # own wording (potentially containing redaction-worthy text) stays
    # server-side, behind `--details` on the CLI, never on the HTTP wire.
    @app.get("/__test/llm-error-provider-text")
    def _raise_llm_auth_error_with_provider_text():
        raise LlmAuthError("some very specific provider-side wording")

    client = TestClient(app)
    response = client.get("/__test/llm-error-provider-text")

    assert_error_envelope(response, status=502, code="LLM_AUTH")
    assert "some very specific provider-side wording" not in response.text
