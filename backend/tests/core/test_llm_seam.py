"""Intent 001 sprint 01 WI2: the seam over OpenRouter chat models.

`service.chat_model()` and `service.usage_of()` are the binding interfaces
WI3 (the CLI) and the qa agent build against; these tests only cover the
seam's own logic (fallback, the pre-construction guard, usage decoding) -
never a real network call. `service.ChatOpenRouter` is monkeypatched to a
recording stub so no real client is ever built.
"""

from dataclasses import dataclass

import pytest

from app.core.llm import service as llm_service
from app.core.llm.errors import LlmConfigurationError


@dataclass
class _FakeSettings:
    openrouter_api_key: str
    chat_model: str = "openai/gpt-4.1-mini"


class _RecordingChatOpenRouter:
    """Stands in for `ChatOpenRouter`: records the kwargs it was built with
    instead of touching the network."""

    last_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs


@pytest.fixture(autouse=True)
def _recording_chat_open_router(monkeypatch):
    _RecordingChatOpenRouter.last_kwargs = None
    monkeypatch.setattr(llm_service, "ChatOpenRouter", _RecordingChatOpenRouter)
    return _RecordingChatOpenRouter


def test_chat_model_falls_back_to_settings_model_and_default_temperature(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: _FakeSettings(openrouter_api_key="key-123", chat_model="anthropic/claude"),
    )

    llm_service.chat_model()

    kwargs = _RecordingChatOpenRouter.last_kwargs
    assert kwargs["model"] == "anthropic/claude"
    assert kwargs["temperature"] == llm_service.DEFAULT_TEMPERATURE
    assert kwargs["api_key"] == "key-123"


def test_chat_model_passes_through_explicit_model_and_temperature(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: _FakeSettings(openrouter_api_key="key-123", chat_model="anthropic/claude"),
    )

    llm_service.chat_model(model="openai/gpt-4o", temperature=0.2)

    kwargs = _RecordingChatOpenRouter.last_kwargs
    assert kwargs["model"] == "openai/gpt-4o"
    assert kwargs["temperature"] == 0.2


def test_chat_model_raises_before_construction_when_api_key_is_blank(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: _FakeSettings(openrouter_api_key=""),
    )

    with pytest.raises(LlmConfigurationError, match="OPENROUTER_API_KEY"):
        llm_service.chat_model()

    assert _RecordingChatOpenRouter.last_kwargs is None


def test_chat_model_raises_when_api_key_is_only_whitespace(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: _FakeSettings(openrouter_api_key="   "),
    )

    with pytest.raises(LlmConfigurationError):
        llm_service.chat_model()

    assert _RecordingChatOpenRouter.last_kwargs is None


class _FakeMessage:
    """Minimal stand-in for `BaseMessage`/`AIMessage`: only carries the two
    attributes `usage_of` reads."""

    def __init__(self, usage_metadata=None, response_metadata=None):
        self.usage_metadata = usage_metadata
        self.response_metadata = response_metadata if response_metadata is not None else {}


def test_usage_of_reads_token_counts_and_cost():
    message = _FakeMessage(
        usage_metadata={"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        response_metadata={"cost": 0.0012},
    )

    usage = llm_service.usage_of(message)

    assert usage.prompt_tokens == 12
    assert usage.completion_tokens == 34
    assert usage.total_tokens == 46
    assert usage.cost_usd == 0.0012


def test_usage_of_degrades_to_zeros_and_none_without_usage_metadata_or_cost():
    message = _FakeMessage(usage_metadata=None, response_metadata={})

    usage = llm_service.usage_of(message)

    assert usage.prompt_tokens == 0
    assert usage.completion_tokens == 0
    assert usage.total_tokens == 0
    assert usage.cost_usd is None


def test_usage_of_degrades_cost_only_when_metadata_present_but_cost_absent():
    message = _FakeMessage(
        usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        response_metadata={},
    )

    usage = llm_service.usage_of(message)

    assert usage.total_tokens == 12
    assert usage.cost_usd is None
