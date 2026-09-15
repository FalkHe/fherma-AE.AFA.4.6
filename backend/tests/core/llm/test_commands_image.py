"""Sprint 05 WI2 — `app llm image` (`app/core/llm/commands.py`).

Drives the command through `typer.testing.CliRunner` against the real CLI
(`app.cli.cli`), monkeypatching `llm_service.generate_image` directly per
the contract fixed in the sprint's research.md — sibling WI1 owns that
function's implementation (it may not exist yet when this file runs, since
WI1 and WI2 run in parallel: `raising=False` on every `monkeypatch.setattr`
below lets this suite stand entirely on the Interfaces contract). These
tests only cover this command's own logic: the `--out` guard runs before
any call, the two-line success output, overwrite behaviour, the OSError
ordering, and that `LlmError` failures share `chat`'s `_report_failure`
helper.

Real image payloads are ~1.7 MB (research.md); every fake here uses a tiny
byte string instead, since only file-identity (byte-for-byte round trip)
and the reported length matter, never a plausible image.
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
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None


@dataclass(frozen=True)
class _FakeImageResult:
    image_bytes: bytes
    media_type: str
    usage: _FakeUsage


def _patch_generate_image(monkeypatch, fn):
    monkeypatch.setattr(llm_service, "generate_image", fn, raising=False)


def test_writes_the_bytes_returned_by_the_service_byte_identical(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"
    payload = b"\x89PNG-fake-bytes"

    def _fake_generate_image(prompt, *, model=None):
        return _FakeImageResult(
            image_bytes=payload,
            media_type="image/png",
            usage=_FakeUsage(prompt_tokens=12, completion_tokens=1120, total_tokens=1132, cost_usd=0.067206),
        )

    _patch_generate_image(monkeypatch, _fake_generate_image)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == payload


def test_prints_exactly_two_stdout_lines_on_success(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"
    payload = b"tiny-bytes"

    def _fake_generate_image(prompt, *, model=None):
        return _FakeImageResult(
            image_bytes=payload,
            media_type="image/png",
            usage=_FakeUsage(prompt_tokens=12, completion_tokens=1120, total_tokens=1132, cost_usd=0.067206),
        )

    _patch_generate_image(monkeypatch, _fake_generate_image)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines == [
        f"wrote {out} ({len(payload)} bytes, image/png)",
        "tokens: prompt=12 completion=1120 total=1132 · cost: $0.067206",
    ]


def test_overwrites_an_existing_file_without_prompting(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"
    out.write_bytes(b"old-bytes-that-must-be-replaced")
    payload = b"new-bytes"

    def _fake_generate_image(prompt, *, model=None):
        return _FakeImageResult(
            image_bytes=payload,
            media_type="image/png",
            usage=_FakeUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=0.01),
        )

    _patch_generate_image(monkeypatch, _fake_generate_image)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 0, result.stderr
    assert out.read_bytes() == payload


def test_missing_out_parent_directory_rejected_before_any_call_exit_code_2(monkeypatch, tmp_path):
    calls = []

    def _fake_generate_image(prompt, *, model=None):
        calls.append(prompt)
        raise AssertionError("must never be called for a bad --out path")

    _patch_generate_image(monkeypatch, _fake_generate_image)

    out = tmp_path / "does-not-exist" / "portrait.png"

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 2
    assert calls == []
    assert not out.exists()


def test_out_parent_that_is_a_file_not_a_directory_rejected_before_any_call(monkeypatch, tmp_path):
    calls = []

    def _fake_generate_image(prompt, *, model=None):
        calls.append(prompt)
        raise AssertionError("must never be called for a bad --out path")

    _patch_generate_image(monkeypatch, _fake_generate_image)

    parent_that_is_a_file = tmp_path / "not-a-directory"
    parent_that_is_a_file.write_bytes(b"i-am-a-file")
    out = parent_that_is_a_file / "portrait.png"

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 2
    assert calls == []


def test_oserror_at_write_time_prints_usage_line_on_stdout_first_then_reason_on_stderr_exit_1(
    monkeypatch, tmp_path
):
    out = tmp_path / "readonly-dir" / "portrait.png"
    out.parent.mkdir()
    out.parent.chmod(0o500)  # read + execute, no write

    def _fake_generate_image(prompt, *, model=None):
        return _FakeImageResult(
            image_bytes=b"payload-bytes",
            media_type="image/png",
            usage=_FakeUsage(prompt_tokens=12, completion_tokens=1120, total_tokens=1132, cost_usd=0.067206),
        )

    _patch_generate_image(monkeypatch, _fake_generate_image)

    try:
        result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])
    finally:
        out.parent.chmod(0o700)  # tmp_path cleanup needs write access back

    assert result.exit_code == 1
    assert result.stdout.splitlines() == [
        "tokens: prompt=12 completion=1120 total=1132 · cost: $0.067206"
    ]
    assert str(out) in result.stderr
    assert not out.exists()


def test_llm_error_goes_through_report_failure_no_file_written_exit_1(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"

    def _boom(prompt, *, model=None):
        raise LlmRateLimitError("rate limited")

    _patch_generate_image(monkeypatch, _boom)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 1
    assert "The AI service could not complete that request." in result.stderr
    assert result.stdout == ""
    assert not out.exists()


def test_base_llm_error_subclass_is_caught_not_just_the_named_ones(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"

    def _boom(prompt, *, model=None):
        raise LlmBadRequestError()

    _patch_generate_image(monkeypatch, _boom)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert result.exit_code == 1
    assert "Traceback" not in result.stderr
    assert not out.exists()


def test_prompt_and_model_are_forwarded(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"
    calls = []

    def _fake_generate_image(prompt, *, model=None):
        calls.append((prompt, model))
        return _FakeImageResult(
            image_bytes=b"bytes",
            media_type="image/png",
            usage=_FakeUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost_usd=None),
        )

    _patch_generate_image(monkeypatch, _fake_generate_image)

    result = runner.invoke(
        cli, ["llm", "image", "a brooding half-orc", "--out", str(out), "--model", "test/image-model"]
    )

    assert result.exit_code == 0, result.stderr
    assert calls == [("a brooding half-orc", "test/image-model")]


class _FakeFailure(LlmRateLimitError):
    """Decoy attributes that must never reach stdout or stderr — the
    security constraint carried over from `chat`'s canary test."""

    def __init__(self, provider_message: str | None) -> None:
        super().__init__(provider_message)
        self.body = "SECRET-BODY sk-or-leak"
        self.headers = {"Authorization": "Bearer sk-or-leak"}
        self.raw_response = "sk-or-leak"


def test_details_flag_prints_the_provider_message(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"

    def _boom(prompt, *, model=None):
        raise _FakeFailure("insufficient quota")

    _patch_generate_image(monkeypatch, _boom)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out), "--details"])

    assert result.exit_code == 1
    assert "details: insufficient quota" in result.stderr


def test_details_flag_never_prints_body_headers_or_raw_response(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"

    def _boom(prompt, *, model=None):
        raise _FakeFailure("insufficient quota")

    _patch_generate_image(monkeypatch, _boom)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out), "--details"])

    combined = result.stdout + result.stderr
    assert "sk-or-leak" not in combined
    assert "SECRET-BODY" not in combined
    assert "Authorization" not in combined


def test_without_details_flag_no_details_line_is_printed(monkeypatch, tmp_path):
    out = tmp_path / "portrait.png"

    def _boom(prompt, *, model=None):
        raise LlmRateLimitError("rate limited")

    _patch_generate_image(monkeypatch, _boom)

    result = runner.invoke(cli, ["llm", "image", "a hero", "--out", str(out)])

    assert "details:" not in result.stderr
