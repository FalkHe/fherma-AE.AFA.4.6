"""qa acceptance tests — sprint 001/05: an image call round-trips and
writes a file that opens (AC3, AC4, AC5).

AC1 ("a real key writes a file that opens as an image") and AC2 ("the same
run prints the call's USD cost") are hand-run by the human against the real
gateway (~$0.067/call) -- there is no automated test for either, per the
sprint brief.

Black-box: every test drives `app.core.llm.service.generate_image()` --
never a private helper -- or the real `app llm image` CLI command, through
a stub OpenRouter gateway wired in at the seam the binding interface names
for this, exactly as `test_errors.py` (sprint 001/02) and
`test_embeddings.py` (sprint 001/04) do: `service.build_sdk_client`
monkeypatched to hand back a real `openrouter.OpenRouter` client built on
`httpx.MockTransport`. No test here ever needs (or sets) a real
`OPENROUTER_API_KEY` -- the suite's own pinned placeholder
(`tests/conftest.py`: `OPENROUTER_API_KEY=test-key`) is never read past the
stubbed client construction, and `tests/conftest.py` pins
`IMAGE_MODEL=test/image-model`.
"""

import base64

import httpx
import openrouter
import pytest
from typer.testing import CliRunner

from app.cli import cli
from app.core.llm import retry as retry_module
from app.core.llm import service as llm_service
from app.core.llm.errors import (
    LlmAuthError,
    LlmBadRequestError,
    LlmBudgetError,
    LlmConfigurationError,
    LlmMalformedError,
    LlmRateLimitError,
    LlmRefusedError,
    LlmTimeoutError,
    LlmUnavailableError,
)
from app.core.settings import get_settings

runner = CliRunner()

CONFIGURED_IMAGE_MODEL = "test/image-model"


def _stub_gateway(monkeypatch, handler):
    """Injects a stub OpenRouter gateway at `service.build_sdk_client`, the
    seam the binding interface names for this -- the only network boundary
    any test here crosses (mirrors `test_errors.py` / `test_embeddings.py`).
    """

    def _build(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)


def _valid_b64() -> str:
    """A tiny, validly-base64-encoded payload -- never a real ~1.7MB
    portrait; only the encoding has to be genuine for these tests."""
    return base64.b64encode(b"tiny-fake-image-bytes").decode()


def _image_body(data, *, usage=None, created=1_700_000_000):
    body = {"created": created, "data": data}
    if usage is not None:
        body["usage"] = usage
    return body


def _status_handler(status_code, message="the provider said no"):
    def handler(request):
        body = {"error": {"code": status_code, "message": message}}
        return httpx.Response(status_code, json=body)

    return handler


def _wrong_type_handler():
    """A 200 that arrives as `text/event-stream` instead of parsed JSON --
    the SDK hands the seam an `EventStream`, not an `ImageGenerationResponse`
    (same trigger `test_errors.py` / `test_embeddings.py` use for their own
    "malformed" case). This is the concrete shape of "the response is the
    wrong type" the binding interface names."""

    def handler(request):
        return httpx.Response(
            200,
            content=b"data: not-a-json-object\n\n",
            headers={"content-type": "text/event-stream"},
        )

    return handler


class TestAC5SeamRaisesAndNeverSubstitutes:
    """Every failure mode raises an `LlmError` subclass; nothing here ever
    returns bytes or lets a file be written on the way out (← AC5)."""

    def test_ac5_blank_api_key_raises_configuration_error_before_any_call(self, monkeypatch):
        # ← AC5
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        get_settings.cache_clear()

        def poison(api_key):
            raise AssertionError("must not build a client with a blank key")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        try:
            with pytest.raises(LlmConfigurationError):
                llm_service.generate_image("a half-elf ranger")
        finally:
            get_settings.cache_clear()

    def test_ac5_blank_prompt_raises_bad_request_before_any_call(self, monkeypatch):
        # ← AC5
        def poison(api_key):
            raise AssertionError("must not build a client for a blank prompt")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        with pytest.raises(LlmBadRequestError):
            llm_service.generate_image("")

    @pytest.mark.parametrize(
        ("status_code", "expected_cls"),
        [
            (400, LlmBadRequestError),
            (401, LlmAuthError),
            (402, LlmBudgetError),
            (403, LlmRefusedError),
            (408, LlmTimeoutError),
            (429, LlmRateLimitError),
            (502, LlmUnavailableError),
        ],
    )
    def test_ac5_each_provider_status_raises_its_class_and_returns_no_result(
        self, monkeypatch, status_code, expected_cls
    ):
        # ← AC5: the sharp case -- a placeholder-substituting seam would
        # still pass a bare `pytest.raises`, so this also proves nothing
        # assignable to a result ever comes back on the failure path.
        _stub_gateway(monkeypatch, _status_handler(status_code, message="provider says no"))
        result = None

        with pytest.raises(expected_cls):
            result = llm_service.generate_image("a half-elf ranger")

        assert result is None

    def test_ac5_empty_data_list_raises_malformed(self, monkeypatch):
        # ← AC5
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body([])))

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a half-elf ranger")

    def test_ac5_undecodable_base64_raises_malformed(self, monkeypatch):
        # ← AC5: schema-valid (`b64_json` is just a string field) but the
        # seam's own base64 decode must fail loudly, not hand back garbage
        # bytes as if they were a portrait.
        data = [{"b64_json": "abcde", "media_type": "image/png"}]
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body(data)))

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a half-elf ranger")

    def test_ac5_wrong_response_type_raises_malformed(self, monkeypatch):
        # ← AC5
        _stub_gateway(monkeypatch, _wrong_type_handler())

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a half-elf ranger")

    def test_ac5_cli_writes_no_file_when_the_provider_refuses(self, monkeypatch, tmp_path):
        # ← AC5: the CLI seam (I2) called through the real
        # `app llm image` command -- a failing seam call must leave the
        # `--out` path untouched, not a placeholder image.
        _stub_gateway(monkeypatch, _status_handler(500, message="provider says no"))
        out_path = tmp_path / "portrait.png"

        result = runner.invoke(
            cli, ["llm", "image", "a half-elf ranger", "--out", str(out_path)]
        )

        assert result.exit_code != 0
        assert not out_path.exists()

    def test_ac5_cli_writes_no_file_when_the_response_is_malformed(self, monkeypatch, tmp_path):
        # ← AC5
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body([])))
        out_path = tmp_path / "portrait.png"

        result = runner.invoke(
            cli, ["llm", "image", "a half-elf ranger", "--out", str(out_path)]
        )

        assert result.exit_code != 0
        assert not out_path.exists()


class TestAC3RequestGoesToOpenRouterWithConfiguredModel:
    """The request reaches OpenRouter's `/api/v1/images` carrying
    `IMAGE_MODEL`, never a Google host -- verifiable from both the real
    request the mock transport sees and the logged request URL (← AC3)."""

    def test_ac3_real_request_host_is_openrouter_and_path_is_api_v1_images(self, monkeypatch):
        # ← AC3: the substance of D1's ruling, asserted from inside the
        # mock transport handler -- this is the actual request the SDK
        # built, not a log line someone could fake.
        captured = {}

        def handler(request):
            captured["request"] = request
            data = [{"b64_json": _valid_b64(), "media_type": "image/png"}]
            return httpx.Response(200, json=_image_body(data))

        _stub_gateway(monkeypatch, handler)

        llm_service.generate_image("a half-elf ranger")

        request = captured["request"]
        assert request.url.host == "openrouter.ai"
        assert "google" not in request.url.host
        assert request.url.path == "/api/v1/images"

    def test_ac3_configured_model_is_sent_never_a_google_model_string(self, monkeypatch):
        # ← AC3
        import json as jsonlib

        captured = {}

        def handler(request):
            captured["body"] = jsonlib.loads(request.content)
            data = [{"b64_json": _valid_b64(), "media_type": "image/png"}]
            return httpx.Response(200, json=_image_body(data))

        _stub_gateway(monkeypatch, handler)

        llm_service.generate_image("a half-elf ranger")

        assert captured["body"]["model"] == CONFIGURED_IMAGE_MODEL

    def test_ac3_logged_request_carries_a_url_ending_in_api_v1_images_and_the_model(
        self, monkeypatch, capsys
    ):
        # ← AC3: the *logged* event, per the binding interface
        # (`llm_image_request` with `url` and `model`, url derived from
        # `get_server_details()`, never a literal).
        from app.core.logging import configure_logging

        configure_logging()

        def handler(request):
            data = [{"b64_json": _valid_b64(), "media_type": "image/png"}]
            return httpx.Response(200, json=_image_body(data))

        _stub_gateway(monkeypatch, handler)
        llm_service.generate_image("a half-elf ranger")

        err = capsys.readouterr().err
        request_lines = [line for line in err.splitlines() if "llm_image_request" in line]
        assert len(request_lines) >= 1
        line = request_lines[0]
        assert "/api/v1/images" in line
        assert CONFIGURED_IMAGE_MODEL in line
        assert "google" not in line.lower()

    def test_ac3_request_is_logged_before_the_call_even_when_it_fails(self, monkeypatch, capsys):
        # ← AC3: logging happens before the call, per the binding
        # interface -- so it must still appear on a failure path, not only
        # after a successful round trip (which a lazily-logging
        # implementation could otherwise pass).
        from app.core.logging import configure_logging

        configure_logging()

        _stub_gateway(monkeypatch, _status_handler(500, message="provider says no"))
        with pytest.raises(LlmUnavailableError):
            llm_service.generate_image("a half-elf ranger")

        err = capsys.readouterr().err
        request_lines = [line for line in err.splitlines() if "llm_image_request" in line]
        assert len(request_lines) >= 1
        assert "/api/v1/images" in request_lines[0]
        assert CONFIGURED_IMAGE_MODEL in request_lines[0]


class TestAC4EightCodesWithoutAKey:
    """The eight sprint-02 codes are raised here too, asserted through the
    mock transport with no real key (← AC4). Retry is live underneath: a
    retryable class makes `llm_retry_attempts` requests, a non-retryable
    one exactly 1."""

    @pytest.mark.parametrize(
        ("status_code", "expected_cls", "expect_full_retry_budget"),
        [
            (400, LlmBadRequestError, False),
            (401, LlmAuthError, False),
            (402, LlmBudgetError, False),
            (403, LlmRefusedError, False),
            (408, LlmTimeoutError, True),
            (429, LlmRateLimitError, True),
            (502, LlmUnavailableError, True),
        ],
    )
    def test_ac4_status_code_raises_its_class_with_expected_attempt_count(
        self, monkeypatch, status_code, expected_cls, expect_full_retry_budget
    ):
        # ← AC4
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return _status_handler(status_code, message="provider says no")(request)

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(expected_cls) as excinfo:
            llm_service.generate_image("a half-elf ranger")

        assert excinfo.value.code is expected_cls.code
        expected_count = get_settings().llm_retry_attempts if expect_full_retry_budget else 1
        assert calls["count"] == expected_count

    def test_ac4_wrong_response_type_raises_malformed_and_is_retried_up_to_its_own_cap(
        self, monkeypatch
    ):
        # ← AC4: `LLM_MALFORMED` is retryable, but capped at
        # `retry.MALFORMED_MAX_ATTEMPTS`, not the full configured budget.
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return _wrong_type_handler()(request)

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a half-elf ranger")

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_ac4_empty_data_raises_malformed_and_is_retried_up_to_its_own_cap(self, monkeypatch):
        # ← AC4
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return httpx.Response(200, json=_image_body([]))

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a half-elf ranger")

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_ac4_blank_prompt_raises_bad_request_before_any_network_call(self, monkeypatch):
        # ← AC4: rejected before any client is even built -- a poison
        # `build_sdk_client` would fail this test if it were ever reached.
        def poison(api_key):
            raise AssertionError("must not build a client for a blank prompt")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        with pytest.raises(LlmBadRequestError):
            llm_service.generate_image("")
