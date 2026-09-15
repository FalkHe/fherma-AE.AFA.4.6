"""Tests for `app llm chat` -- WI3, sprint 001-01.

Owns the CLI wiring only: seam calls, plain vs. --stream output shape and
the usage line, and the LlmError -> exit 1 contract. `llm_service.chat_model`
is always monkeypatched -- these tests never touch the network. The actual
behaviour of `llm_service` / `errors` is WI2's and lives in
`test_llm_service.py`, owned by the qa agent.
"""

from dataclasses import dataclass

import pytest
from typer.testing import CliRunner

from app.cli import cli
from app.core.llm import service as llm_service
from app.core.llm.commands import llm_app
from app.core.llm.errors import LlmError

runner = CliRunner()


@dataclass(frozen=True)
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None


class FakeMessage:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text


class FakeChunk:
    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str:
        return self._text

    def __add__(self, other: "FakeChunk") -> "FakeChunk":
        return FakeChunk(self._text + other._text)


class FakeChatModel:
    def __init__(self, answer: str = "hello there", chunks: list[str] | None = None) -> None:
        self._answer = answer
        self._chunks = chunks or ["hel", "lo the", "re"]

    def invoke(self, prompt: str) -> FakeMessage:
        return FakeMessage(self._answer)

    def stream(self, prompt: str):
        for piece in self._chunks:
            yield FakeChunk(piece)


def test_plain_path_prints_answer_then_one_usage_line(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_service, "chat_model", lambda **kwargs: FakeChatModel())
    monkeypatch.setattr(llm_service, "usage_of", lambda message: FakeUsage(10, 5, 15, 0.001234))

    result = runner.invoke(llm_app, ["hi"])

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines[0] == "hello there"
    assert lines[1] == "tokens: prompt=10 completion=5 total=15 · cost: $0.001234"
    assert len(lines) == 2


def test_stream_path_prints_answer_then_exactly_one_usage_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm_service, "chat_model", lambda **kwargs: FakeChatModel())
    seen_totals = []

    def fake_usage_of(message: FakeChunk) -> FakeUsage:
        seen_totals.append(message.text)
        return FakeUsage(3, 4, 7, None)

    monkeypatch.setattr(llm_service, "usage_of", fake_usage_of)

    result = runner.invoke(llm_app, ["hi", "--stream"])

    assert result.exit_code == 0
    assert "hello there" in result.stdout
    usage_lines = [line for line in result.stdout.splitlines() if line.startswith("tokens:")]
    assert usage_lines == ["tokens: prompt=3 completion=4 total=7 · cost: unavailable"]
    # usage_of must be called on the fully accumulated message, not a chunk
    assert seen_totals == ["hello there"]


def test_model_and_temperature_options_reach_the_seam(monkeypatch: pytest.MonkeyPatch) -> None:
    received = {}

    def fake_chat_model(*, model=None, temperature=None):
        received["model"] = model
        received["temperature"] = temperature
        return FakeChatModel()

    monkeypatch.setattr(llm_service, "chat_model", fake_chat_model)
    monkeypatch.setattr(llm_service, "usage_of", lambda message: FakeUsage(1, 1, 2, None))

    result = runner.invoke(llm_app, ["hi", "--model", "some/model", "--temperature", "0.4"])

    assert result.exit_code == 0
    assert received == {"model": "some/model", "temperature": 0.4}


def test_options_default_to_none_when_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    received = {}

    def fake_chat_model(*, model=None, temperature=None):
        received["model"] = model
        received["temperature"] = temperature
        return FakeChatModel()

    monkeypatch.setattr(llm_service, "chat_model", fake_chat_model)
    monkeypatch.setattr(llm_service, "usage_of", lambda message: FakeUsage(1, 1, 2, None))

    result = runner.invoke(llm_app, ["hi"])

    assert result.exit_code == 0
    assert received == {"model": None, "temperature": None}


def test_llm_error_exits_1_with_message_on_stderr_and_no_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_llm_error(**kwargs):
        raise LlmError("openrouter is unreachable")

    monkeypatch.setattr(llm_service, "chat_model", raise_llm_error)

    result = runner.invoke(llm_app, ["hi"])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "openrouter is unreachable"
    assert "Traceback" not in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_registered_on_the_top_level_cli_as_llm_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm_service, "chat_model", lambda **kwargs: FakeChatModel())
    monkeypatch.setattr(llm_service, "usage_of", lambda message: FakeUsage(1, 1, 2, None))

    result = runner.invoke(cli, ["llm", "chat", "hi"])

    assert result.exit_code == 0
    assert "hello there" in result.stdout
