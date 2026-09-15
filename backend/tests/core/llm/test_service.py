"""Sprint 01 AC3 — `--model` / `--temperature` reach `ChatOpenRouter`;
omitted, the settings values (`CHAT_MODEL`) and the seam's
`DEFAULT_TEMPERATURE` do (binding interface I1, `app/core/llm/service.py`).

Driven directly against `llm_service.chat_model`, not through the CLI: I1
names this exact behaviour and hands QA the monkeypatch seam
(`service.ChatOpenRouter`) to test it without a real key or a network call.
`tests/conftest.py` pins `OPENROUTER_API_KEY=test-key` and
`CHAT_MODEL=test/model` before `app` is imported and clears the settings
cache, so `get_settings().chat_model` below is that pinned value.
"""

from app.core.llm import service as llm_service
from app.core.settings import get_settings


def test_ac3_model_and_temperature_override_per_call(recording_chat_open_router, monkeypatch):
    # ← AC3
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    llm_service.chat_model(model="openai/gpt-4.1", temperature=0.2)

    call = recording_chat_open_router.calls[-1]
    assert call["model"] == "openai/gpt-4.1"
    assert call["temperature"] == 0.2


def test_ac3_omitted_model_and_temperature_fall_back_to_settings_and_default(
    recording_chat_open_router, monkeypatch
):
    # ← AC3
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    llm_service.chat_model()

    call = recording_chat_open_router.calls[-1]
    assert call["model"] == get_settings().chat_model
    assert call["temperature"] == llm_service.DEFAULT_TEMPERATURE
