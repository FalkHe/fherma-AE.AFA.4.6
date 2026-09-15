"""qa acceptance tests — sprint 001/05: an image call round-trips and reports
what it cost (AC3, AC5).

AC1/AC2 ("a real key returns a portrait plus a file that opens") are
hand-run by the human against the real gateway; there is no automated test
for either, per the sprint brief - a live call costs real money.

Black-box: every test drives `app.core.llm.service.generate_image()` -
never a private helper - through a stub OpenRouter gateway wired in at the
seam the binding interface names for this, exactly as `test_embeddings.py`
(sprint 001/04) does: `service.build_sdk_client` monkeypatched to hand back
a real `openrouter.OpenRouter` client built on `httpx.MockTransport`. No
test here ever needs (or sets) a real `OPENROUTER_API_KEY` - the suite's
own pinned placeholder (`tests/conftest.py`: `OPENROUTER_API_KEY=test-key`)
is never read past the stubbed client construction.

`tests/conftest.py` pins `IMAGE_MODEL=test/image-model`.
"""

import base64
import json as jsonlib
import re

import httpx
import openrouter
import pytest
import structlog

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

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
_PNG_BYTES = b"\x89PNG\r\n\x1a\nnot-a-real-png-but-good-enough"
_PNG_B64 = base64.b64encode(_PNG_BYTES).decode("ascii")


def _plain(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _stub_gateway(monkeypatch, handler):
    """Injects a stub OpenRouter gateway at `service.build_sdk_client`, the
    seam the binding interface names for this — the only network boundary
    any test here crosses (mirrors `test_embeddings.py`)."""

    def _build(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)


def _image_body(*, data=None, usage=None, media_type="image/png"):
    item = {"b64_json": _PNG_B64}
    if media_type is not None:
        item["media_type"] = media_type
    body = {"created": 0, "data": data if data is not None else [item]}
    if usage is not None:
        body["usage"] = usage
    return body


def _status_handler(status_code, message="the provider said no"):
    def handler(request):
        body = {"error": {"code": status_code, "message": message}}
        return httpx.Response(status_code, json=body)

    return handler


@pytest.fixture
def configured_logging():
    """Mirrors `test_retry.py`: restores structlog's global defaults on the
    way out only; `configure_logging()` itself must run inside the test
    body, after `capsys` has swapped in its call-phase buffer."""
    yield
    structlog.reset_defaults()


class TestAC3RequestGoesToOpenRouter:
    """The request lands on the OpenRouter SDK's own `/images` endpoint,
    carrying the resolved model - proven both on the wire (the mock
    transport sees the real request) and in the log line the seam emits
    before the call, whose `url` is derived from the client's own server
    details rather than a hardcoded literal (← AC3)."""

    def test_ac3_request_hits_the_sdk_server_url_and_path_with_the_resolved_model(
        self, monkeypatch
    ):
        # ← AC3
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            captured["body"] = jsonlib.loads(request.content)
            return httpx.Response(200, json=_image_body())

        _stub_gateway(monkeypatch, handler)

        llm_service.generate_image("a stoic half-orc ranger")

        assert captured["url"] == "https://openrouter.ai/api/v1/images"
        assert captured["body"]["model"] == "test/image-model"
        assert captured["body"]["prompt"] == "a stoic half-orc ranger"

    def test_ac3_explicit_model_overrides_the_configured_default(self, monkeypatch):
        # ← AC3
        captured = {}

        def handler(request):
            captured["body"] = jsonlib.loads(request.content)
            return httpx.Response(200, json=_image_body())

        _stub_gateway(monkeypatch, handler)

        llm_service.generate_image("a prompt", model="other/model")

        assert captured["body"]["model"] == "other/model"

    def test_ac3_logs_the_derived_url_and_model_before_the_call(
        self, monkeypatch, capsys, configured_logging
    ):
        # ← AC3: the point of this line is that it is *derived*, not a
        # literal - a hardcoded string would assert nothing about where the
        # request actually goes.
        from app.core.logging import configure_logging

        configure_logging()
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body()))

        llm_service.generate_image("a prompt")

        err = _plain(capsys.readouterr().err)
        assert "llm_image_request" in err
        assert "https://openrouter.ai/api/v1/images" in err
        assert "test/image-model" in err

    def test_ac3_only_model_and_prompt_are_sent(self, monkeypatch):
        # ← AC3: never `n`, `stream`, `resolution`, `aspect_ratio` or
        # `output_format`.
        captured = {}

        def handler(request):
            captured["body"] = jsonlib.loads(request.content)
            return httpx.Response(200, json=_image_body())

        _stub_gateway(monkeypatch, handler)

        llm_service.generate_image("a prompt")

        forbidden = {"n", "stream", "resolution", "aspect_ratio", "output_format"}
        assert forbidden.isdisjoint(captured["body"].keys())


class TestImageResultRoundTrip:
    """The returned `ImageResult` decodes the provider's base64 payload and
    carries its usage, matching D3's token-plus-USD requirement."""

    def test_decodes_b64_json_into_image_bytes(self, monkeypatch):
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body()))

        result = llm_service.generate_image("a prompt")

        assert result.image_bytes == _PNG_BYTES

    def test_media_type_present_on_the_response_is_used(self, monkeypatch):
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(
                200, json=_image_body(media_type="image/svg+xml")
            ),
        )

        result = llm_service.generate_image("a prompt")

        assert result.media_type == "image/svg+xml"

    def test_media_type_absent_on_the_response_defaults_to_png(self, monkeypatch):
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(200, json=_image_body(media_type=None)),
        )

        result = llm_service.generate_image("a prompt")

        assert result.media_type == "image/png"

    def test_usage_tokens_and_cost_copy_across(self, monkeypatch):
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json=_image_body(
                    usage={
                        "prompt_tokens": 12,
                        "completion_tokens": 1120,
                        "total_tokens": 1132,
                        "cost": 0.067206,
                    }
                ),
            ),
        )

        result = llm_service.generate_image("a prompt")

        assert result.usage.prompt_tokens == 12
        assert result.usage.completion_tokens == 1120
        assert result.usage.total_tokens == 1132
        assert result.usage.cost_usd == 0.067206

    def test_usage_with_absent_cost_reads_back_as_unset_not_none_but_seam_returns_none(
        self, monkeypatch
    ):
        # ← the `Unset()` trap the research flagged: absent `cost` must
        # never reach `round()` as anything but `None`.
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json=_image_body(
                    usage={"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
                ),
            ),
        )

        result = llm_service.generate_image("a prompt")

        assert result.usage.cost_usd is None
        assert isinstance(result.usage.cost_usd, float | type(None))

    def test_usage_absent_entirely_defaults_to_zero_counts_and_no_cost(self, monkeypatch):
        _stub_gateway(monkeypatch, lambda request: httpx.Response(200, json=_image_body()))

        result = llm_service.generate_image("a prompt")

        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0
        assert result.usage.total_tokens == 0
        assert result.usage.cost_usd is None


class TestAC5RaisesNeverSubstitutes:
    """Nothing in this function may return a placeholder image: every
    failure mode raises an `LlmError` instead (← AC5)."""

    def test_blank_api_key_raises_configuration_error_before_any_network_call(
        self, monkeypatch
    ):
        monkeypatch.setenv("OPENROUTER_API_KEY", "")
        get_settings.cache_clear()

        def poison(api_key):
            raise AssertionError("must not build a client with a blank key")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        try:
            with pytest.raises(LlmConfigurationError):
                llm_service.generate_image("a prompt")
        finally:
            get_settings.cache_clear()

    def test_blank_prompt_raises_bad_request_before_any_network_call(self, monkeypatch):
        def poison(api_key):
            raise AssertionError("must not build a client for a blank prompt")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        with pytest.raises(LlmBadRequestError):
            llm_service.generate_image("   ")

    def test_empty_data_list_raises_malformed(self, monkeypatch):
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return httpx.Response(200, json=_image_body(data=[]))

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a prompt")

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_unparseable_b64_json_raises_malformed_not_a_foreign_binascii_error(
        self, monkeypatch
    ):
        # ← the trap the research flagged: `binascii.Error` is otherwise
        # unclassified and would escape as a foreign exception.
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return httpx.Response(
                200, json=_image_body(data=[{"b64_json": "not-valid-base64!!!"}])
            )

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a prompt")

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_non_image_generation_response_raises_malformed(self, monkeypatch):
        # ← a 200 that comes back as `text/event-stream` instead of a
        # parsed `ImageGenerationResponse` - the shape the SDK itself
        # returns for a streaming-capable response even when `stream` was
        # never requested.
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return httpx.Response(
                200,
                content=b"data: not-a-json-object\n\n",
                headers={"content-type": "text/event-stream"},
            )

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.generate_image("a prompt")

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_never_returns_a_placeholder_on_failure(self, monkeypatch):
        # ← AC5's headline claim, made concrete: a failing call has no
        # return value at all to inspect for a placeholder - it raises.
        _stub_gateway(monkeypatch, _status_handler(500))

        with pytest.raises(LlmUnavailableError):
            result = llm_service.generate_image("a prompt")
            pytest.fail(f"must have raised, not returned {result!r}")


class TestTheEightCodes:
    """The same eight `LlmError` classes sprint 02/03 established are
    raised here too, via the shared `classify()` / `call_with_retry()`
    (← research: 'AC4 holds by construction, no parallel error path')."""

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
    def test_status_code_raises_its_class_with_expected_attempt_count(
        self, monkeypatch, status_code, expected_cls, expect_full_retry_budget
    ):
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            return _status_handler(status_code, message="provider says no")(request)

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(expected_cls) as excinfo:
            llm_service.generate_image("a prompt")

        assert excinfo.value.code is expected_cls.code
        expected_count = get_settings().llm_retry_attempts if expect_full_retry_budget else 1
        assert calls["count"] == expected_count
