"""Tests for `agent/model_call.py` (sprint 011-06)."""

from langchain_core.messages import AIMessage

from app.core.llm import service as llm_service
from app.modules.game.agent import model_call


def test_to_usage_sums_two_scripted_messages() -> None:
    first = AIMessage(
        content="a",
        usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        response_metadata={"cost": 0.01},
    )
    second = AIMessage(
        content="b",
        usage_metadata={"input_tokens": 3, "output_tokens": 7, "total_tokens": 10},
        response_metadata={"cost": 0.02},
    )

    usage = model_call.to_usage([first, second])

    assert usage.prompt_tokens == 13
    assert usage.completion_tokens == 12
    assert usage.cost == 0.03


def test_build_model_calls_the_core_seam(monkeypatch) -> None:
    sentinel = object()
    calls: list[dict] = []

    def _fake_chat_model(**kwargs):
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(llm_service, "chat_model", _fake_chat_model)

    assert model_call.build_model() is sentinel
    assert calls == [{}]
