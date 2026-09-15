"""Sprint 02 WI4 — `--details` and the one generic failure line
(`app/core/llm/commands.py`, decision D2).

Isolated from WI2 (`core/llm/errors.py`) and WI3 (`core/llm/service.py`):
this drives `app llm chat` through `CliRunner`, monkeypatching the seam
helpers `llm_service.chat` / `llm_service.chat_stream` directly (the
contract fixed in the sprint's research.md, not their implementation) and
using a local stand-in `LlmError` subclass so these tests do not depend on
either sibling landing first.
"""

from langchain_core.messages import AIMessage, AIMessageChunk
from typer.testing import CliRunner

from app.cli import cli
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmRateLimitError

runner = CliRunner()


class _FakeFailure(LlmRateLimitError):
    """One of WI2's eight provider failure classes, plus decoy attributes
    that must never reach stdout or stderr (the security constraint -
    `.body`/`.headers`/`.raw_response` carry the OpenRouter API key on the
    real exceptions)."""

    def __init__(self, provider_message: str | None) -> None:
        super().__init__(provider_message)
        self.body = "SECRET-BODY sk-or-leak"
        self.headers = {"Authorization": "Bearer sk-or-leak"}
        self.raw_response = "sk-or-leak"


def test_generic_line_on_stderr_and_exit_1_for_any_llm_error(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        raise _FakeFailure("rate limited")

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])

    assert result.exit_code == 1
    assert "The AI service could not complete that request." in result.stderr
    assert result.stdout == ""


def test_generic_line_never_contains_the_error_code(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        # `_FakeFailure` inherits `code = ErrorCode.LLM_RATE_LIMIT` from
        # `LlmRateLimitError` - the generic line must never surface it.
        raise _FakeFailure("rate limited")

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])

    assert "LLM_RATE_LIMIT" not in result.stderr
    assert "LLM_RATE_LIMIT" not in result.stdout


def test_without_details_flag_no_details_line_is_printed(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        raise _FakeFailure("rate limited")

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])

    assert "details:" not in result.stderr


def test_details_flag_prints_the_provider_message(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        raise _FakeFailure("insufficient quota")

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--details"])

    assert result.exit_code == 1
    assert "details: insufficient quota" in result.stderr


def test_details_flag_reports_no_message_when_provider_message_is_none(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        raise _FakeFailure(None)

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--details"])

    assert "details: the provider gave no message." in result.stderr


def test_details_flag_never_prints_body_headers_or_raw_response(monkeypatch):
    def _boom(prompt, *, model=None, temperature=None):
        raise _FakeFailure("insufficient quota")

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--details"])

    combined = result.stdout + result.stderr
    assert "sk-or-leak" not in combined
    assert "SECRET-BODY" not in combined
    assert "Authorization" not in combined


def test_details_flag_on_configuration_error_does_not_crash(monkeypatch):
    # `LlmConfigurationError` has no `provider_message` attribute at all
    # (sprint 01, unchanged by this sprint) - `--details` must degrade to
    # the "no message" line rather than raising `AttributeError`.
    from app.core.llm.errors import LlmConfigurationError

    def _boom(prompt, *, model=None, temperature=None):
        raise LlmConfigurationError()

    monkeypatch.setattr(llm_service, "chat", _boom)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--details"])

    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY" in result.stderr
    assert "details: the provider gave no message." in result.stderr


def test_plain_chat_path_uses_the_chat_seam_helper(monkeypatch):
    calls = []

    def _fake_chat(prompt, *, model=None, temperature=None):
        calls.append((prompt, model, temperature))
        return AIMessage(
            content="A dazed creature can't take actions.",
            usage_metadata={"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
            response_metadata={},
        )

    monkeypatch.setattr(llm_service, "chat", _fake_chat)

    result = runner.invoke(
        cli,
        [
            "llm",
            "chat",
            "Name one D&D condition.",
            "--model",
            "openai/gpt-4.1",
            "--temperature",
            "0.2",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert calls == [("Name one D&D condition.", "openai/gpt-4.1", 0.2)]
    assert "A dazed creature can't take actions." in result.stdout


def test_stream_path_uses_the_chat_stream_seam_helper_and_fails_mid_stream(monkeypatch):
    def _fake_chat_stream(prompt, *, model=None, temperature=None):
        yield AIMessageChunk(content="A dazed creature ")
        raise _FakeFailure("stream broke")

    monkeypatch.setattr(llm_service, "chat_stream", _fake_chat_stream)

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--stream"])

    assert result.exit_code == 1
    assert "A dazed creature " in result.stdout
    assert "The AI service could not complete that request." in result.stderr
