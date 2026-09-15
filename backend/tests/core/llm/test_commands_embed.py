"""Sprint 04 WI3 — `app llm embed` (`app/core/llm/commands.py`).

Drives the command through `typer.testing.CliRunner` against the real CLI
(`app.cli.cli`), monkeypatching `llm_service.embed_texts` directly per the
contract fixed in the sprint's research.md - sibling WI2 owns that
function's implementation, WI4 owns its own round-trip tests
(`test_embeddings.py`). These tests only cover this command's own logic:
argument wiring, output shape, and that failures share `chat`'s
`_report_failure` helper (redaction included).
"""

from dataclasses import dataclass

from typer.testing import CliRunner

from app.cli import cli
from app.core.llm import service as llm_service
from app.core.llm.errors import LlmBadRequestError, LlmRateLimitError

runner = CliRunner()


@dataclass(frozen=True)
class _FakeUsage:
    prompt_tokens: int
    total_tokens: int
    cost_usd: float | None
    completion_tokens: int = 0


@dataclass(frozen=True)
class _FakeEmbeddingResult:
    vectors: list[list[float]]
    usage: _FakeUsage


def test_prints_one_length_line_per_vector_in_order_then_usage_line(monkeypatch):
    def _fake_embed_texts(texts, *, model=None):
        return _FakeEmbeddingResult(
            vectors=[[0.0] * 1536, [0.0] * 1536],
            usage=_FakeUsage(prompt_tokens=7, total_tokens=7, cost_usd=1e-06),
        )

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "a", "b"])

    assert result.exit_code == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "vector 1: length=1536"
    assert lines[1] == "vector 2: length=1536"
    assert lines[2] == "tokens: prompt=7 total=7 · cost: $0.000001"


def test_zero_cost_prints_six_zeros(monkeypatch):
    def _fake_embed_texts(texts, *, model=None):
        return _FakeEmbeddingResult(
            vectors=[[0.0]],
            usage=_FakeUsage(prompt_tokens=1, total_tokens=1, cost_usd=0.0),
        )

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout.splitlines()[-1] == "tokens: prompt=1 total=1 · cost: $0.000000"


def test_nonzero_cost_below_display_precision_is_never_shown_as_zero(monkeypatch):
    def _fake_embed_texts(texts, *, model=None):
        return _FakeEmbeddingResult(
            vectors=[[0.0]],
            usage=_FakeUsage(prompt_tokens=5, total_tokens=5, cost_usd=1e-07),
        )

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert result.exit_code == 0, result.stderr
    usage_line = result.stdout.splitlines()[-1]
    assert usage_line == "tokens: prompt=5 total=5 · cost: <$0.000001"
    assert "$0.000000" not in usage_line


def test_usage_line_has_no_completion_field(monkeypatch):
    def _fake_embed_texts(texts, *, model=None):
        return _FakeEmbeddingResult(
            vectors=[[0.0] * 4],
            usage=_FakeUsage(prompt_tokens=3, total_tokens=3, cost_usd=None),
        )

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert result.exit_code == 0, result.stderr
    usage_line = result.stdout.splitlines()[-1]
    assert "completion=" not in usage_line
    assert usage_line == "tokens: prompt=3 total=3 · cost: unavailable"


def test_texts_are_positional_and_space_separated(monkeypatch):
    calls = []

    def _fake_embed_texts(texts, *, model=None):
        calls.append((texts, model))
        return _FakeEmbeddingResult(vectors=[[0.0]] * len(texts), usage=_FakeUsage(0, 0, None))

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "one fish", "two fish", "red fish"])

    assert result.exit_code == 0, result.stderr
    assert calls == [(["one fish", "two fish", "red fish"], None)]


def test_model_option_is_forwarded(monkeypatch):
    calls = []

    def _fake_embed_texts(texts, *, model=None):
        calls.append((texts, model))
        return _FakeEmbeddingResult(vectors=[[0.0]], usage=_FakeUsage(0, 0, None))

    monkeypatch.setattr(llm_service, "embed_texts", _fake_embed_texts)

    result = runner.invoke(cli, ["llm", "embed", "a", "--model", "test/embedding-model"])

    assert result.exit_code == 0, result.stderr
    assert calls == [(["a"], "test/embedding-model")]


def test_generic_line_on_stderr_and_exit_1_for_any_llm_error(monkeypatch):
    def _boom(texts, *, model=None):
        raise LlmRateLimitError("rate limited")

    monkeypatch.setattr(llm_service, "embed_texts", _boom)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert result.exit_code == 1
    assert "The AI service could not complete that request." in result.stderr
    assert result.stdout == ""


def test_base_llm_error_subclass_is_caught_not_just_the_named_ones(monkeypatch):
    def _boom(texts, *, model=None):
        raise LlmBadRequestError()

    monkeypatch.setattr(llm_service, "embed_texts", _boom)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert result.exit_code == 1
    assert "Traceback" not in result.stderr


def test_without_details_flag_no_details_line_is_printed(monkeypatch):
    def _boom(texts, *, model=None):
        raise LlmRateLimitError("rate limited")

    monkeypatch.setattr(llm_service, "embed_texts", _boom)

    result = runner.invoke(cli, ["llm", "embed", "a"])

    assert "details:" not in result.stderr


class _FakeFailure(LlmRateLimitError):
    """Decoy attributes that must never reach stdout or stderr - the
    security constraint carried over from `chat`'s canary test."""

    def __init__(self, provider_message: str | None) -> None:
        super().__init__(provider_message)
        self.body = "SECRET-BODY sk-or-leak"
        self.headers = {"Authorization": "Bearer sk-or-leak"}
        self.raw_response = "sk-or-leak"


def test_details_flag_prints_the_provider_message(monkeypatch):
    def _boom(texts, *, model=None):
        raise _FakeFailure("insufficient quota")

    monkeypatch.setattr(llm_service, "embed_texts", _boom)

    result = runner.invoke(cli, ["llm", "embed", "a", "--details"])

    assert result.exit_code == 1
    assert "details: insufficient quota" in result.stderr


def test_details_flag_never_prints_body_headers_or_raw_response(monkeypatch):
    def _boom(texts, *, model=None):
        raise _FakeFailure("insufficient quota")

    monkeypatch.setattr(llm_service, "embed_texts", _boom)

    result = runner.invoke(cli, ["llm", "embed", "a", "--details"])

    combined = result.stdout + result.stderr
    assert "sk-or-leak" not in combined
    assert "SECRET-BODY" not in combined
    assert "Authorization" not in combined
