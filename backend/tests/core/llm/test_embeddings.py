"""qa acceptance tests — sprint 001/04: an embedding call round-trips and
reports what it cost (AC3, AC4, AC5).

AC1/AC2 ("a real key returns a 1536-wide vector plus its usage line") are
hand-run by the human against the real gateway; there is no automated test
for either, per the sprint brief.

Black-box: every test drives `app.core.llm.service.embed_texts()` — never a
private helper — through a stub OpenRouter gateway wired in at the seam the
binding interface names for this, exactly as `test_errors.py` (sprint
001/02) does for `chat()`: `service.build_sdk_client` monkeypatched to hand
back a real `openrouter.OpenRouter` client built on `httpx.MockTransport`.
No test here ever needs (or sets) a real `OPENROUTER_API_KEY` — the suite's
own pinned placeholder (`tests/conftest.py`: `OPENROUTER_API_KEY=test-key`)
is never read past the stubbed client construction.

`tests/conftest.py` pins `EMBEDDING_MODEL=test/embedding-model` and
`EMBEDDING_DIMENSIONS=4`, so every fixture response below returns 4-wide
vectors.
"""

import json as jsonlib

import httpx
import openrouter
import pytest

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


def _stub_gateway(monkeypatch, handler):
    """Injects a stub OpenRouter gateway at `service.build_sdk_client`, the
    seam the binding interface names for this — the only network boundary
    any test here crosses (mirrors `test_errors.py`)."""

    def _build(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)


def _embeddings_body(data, *, usage=None):
    body = {"data": data, "model": "test/embedding-model", "object": "list"}
    if usage is not None:
        body["usage"] = usage
    return body


def _status_handler(status_code, message="the provider said no"):
    def handler(request):
        body = {"error": {"code": status_code, "message": message}}
        return httpx.Response(status_code, json=body)

    return handler


class TestAC3RequestOrder:
    """Several texts in one call return one vector each, in request order —
    even when the response's `index` values arrive shuffled, or are absent
    altogether (← AC3)."""

    def test_ac3_shuffled_index_values_still_return_vectors_in_request_order(
        self, monkeypatch
    ):
        # ← AC3: the sharp case — response `data` arrives out of order, but
        # each item's explicit `index` says where it really belongs.
        data = [
            {"embedding": [20.0, 20.0, 20.0, 20.0], "object": "embedding", "index": 2},
            {"embedding": [0.0, 0.0, 0.0, 0.0], "object": "embedding", "index": 0},
            {"embedding": [10.0, 10.0, 10.0, 10.0], "object": "embedding", "index": 1},
        ]
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json=_embeddings_body(
                    data, usage={"prompt_tokens": 9, "total_tokens": 9, "cost": 0.002}
                ),
            ),
        )

        result = llm_service.embed_texts(["a", "b", "c"])

        assert result.vectors == [
            [0.0, 0.0, 0.0, 0.0],
            [10.0, 10.0, 10.0, 10.0],
            [20.0, 20.0, 20.0, 20.0],
        ]

    def test_ac3_missing_index_values_keep_response_order(self, monkeypatch):
        # ← AC3: no item carries an `index` at all — response order is kept.
        data = [
            {"embedding": [0.0, 0.0, 0.0, 0.0], "object": "embedding"},
            {"embedding": [1.0, 1.0, 1.0, 1.0], "object": "embedding"},
        ]
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(200, json=_embeddings_body(data)),
        )

        result = llm_service.embed_texts(["a", "b"])

        assert result.vectors == [[0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0]]

    def test_ac3_absent_usage_defaults_to_zero_counts_and_no_cost(self, monkeypatch):
        # ← AC3: the round trip's other half — vectors *and* usage come
        # back together, even when the provider sends no `usage` block.
        data = [{"embedding": [0.0, 0.0, 0.0, 0.0], "object": "embedding", "index": 0}]
        _stub_gateway(
            monkeypatch,
            lambda request: httpx.Response(200, json=_embeddings_body(data)),
        )

        result = llm_service.embed_texts(["a"])

        assert result.usage.prompt_tokens == 0
        assert result.usage.completion_tokens == 0
        assert result.usage.total_tokens == 0
        assert result.usage.cost_usd is None


class TestAC5NoDimensionsSentAndWidthEnforced:
    """No `dimensions` parameter is ever sent; the model's native width is
    what `EMBEDDING_DIMENSIONS` must match — a mismatch refuses rather than
    degrades (← AC5)."""

    def test_ac5_serialised_request_body_has_no_dimensions_key(self, monkeypatch):
        # ← AC5
        captured = {}

        def handler(request):
            captured["body"] = jsonlib.loads(request.content)
            data = [{"embedding": [0.0, 0.0, 0.0, 0.0], "object": "embedding", "index": 0}]
            return httpx.Response(200, json=_embeddings_body(data))

        _stub_gateway(monkeypatch, handler)

        llm_service.embed_texts(["a"])

        assert "dimensions" not in captured["body"]

    def test_ac5_width_mismatch_raises_configuration_error_naming_env_vars_and_width(
        self, monkeypatch
    ):
        # ← AC5: the returned vector is 3-wide; the pinned setting is 4 —
        # this must refuse loudly, not silently truncate or pad.
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            data = [{"embedding": [1.0, 2.0, 3.0], "object": "embedding", "index": 0}]
            return httpx.Response(
                200, json=_embeddings_body(data, usage={"prompt_tokens": 1, "total_tokens": 1})
            )

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmConfigurationError) as excinfo:
            llm_service.embed_texts(["a"])

        message = str(excinfo.value)
        assert "EMBEDDING_MODEL" in message
        assert "EMBEDDING_DIMENSIONS" in message
        assert "3" in message
        # A misconfiguration cannot be fixed by retrying it.
        assert calls["count"] == 1


class TestAC4EightCodesWithoutAKey:
    """The eight sprint-02 codes are raised here too, asserted through the
    mock transport with no key (← AC4). Retry is live underneath: a
    retryable class makes `llm_retry_attempts` requests; a non-retryable
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
            llm_service.embed_texts(["a"])

        assert excinfo.value.code is expected_cls.code
        expected_count = (
            get_settings().llm_retry_attempts if expect_full_retry_budget else 1
        )
        assert calls["count"] == expected_count

    def test_ac4_sse_string_response_raises_malformed_and_is_retried_up_to_its_own_cap(
        self, monkeypatch
    ):
        # ← AC4: an SSE `str` body — the shape the SDK itself returns when a
        # 200 comes back as `text/event-stream` instead of parsed JSON.
        # `LLM_MALFORMED` is retryable, but capped at
        # `retry.MALFORMED_MAX_ATTEMPTS`, not the full configured budget.
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
            llm_service.embed_texts(["a"])

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_ac4_data_length_mismatch_raises_malformed(self, monkeypatch):
        # ← AC4: two texts requested, one vector returned — a shape the SDK
        # parses fine but the seam itself must refuse.
        calls = {"count": 0}

        def handler(request):
            calls["count"] += 1
            data = [{"embedding": [0.0, 0.0, 0.0, 0.0], "object": "embedding", "index": 0}]
            return httpx.Response(200, json=_embeddings_body(data))

        _stub_gateway(monkeypatch, handler)

        with pytest.raises(LlmMalformedError):
            llm_service.embed_texts(["a", "b"])

        assert calls["count"] == retry_module.MALFORMED_MAX_ATTEMPTS

    def test_ac4_empty_texts_raises_bad_request_before_any_network_call(self, monkeypatch):
        # ← AC4: rejected before any client is even built — a poison
        # `build_sdk_client` would fail this test if it were ever reached.
        def poison(api_key):
            raise AssertionError("must not build a client for empty input")

        monkeypatch.setattr(llm_service, "build_sdk_client", poison)

        with pytest.raises(LlmBadRequestError):
            llm_service.embed_texts([])
