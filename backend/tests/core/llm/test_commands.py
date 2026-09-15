"""Sprint 01 AC2, AC4, AC5 — `app llm chat` (binding interface I3,
`app/core/llm/commands.py`, registered in `app/cli.py` as `cli.add_typer(
llm_app, name="llm")`).

Driven through `typer.testing.CliRunner` against the real `cli`
(`app.cli.cli`), per `tests/content/test_cli.py`'s style. The only fake is
`ChatOpenRouter` itself (see `conftest.py`); `llm_service.chat_model` and
`usage_of` run for real, so these are full round-trips from the CLI down to
the (faked) network boundary. Fed real `langchain_core.messages.AIMessage` /
`AIMessageChunk` objects, so `.text`, `.usage_metadata`,
`.response_metadata` and chunk `+` accumulation all behave exactly as the
real `ChatOpenRouter` replies would.
"""

import httpx
import openrouter
from langchain_core.messages import AIMessage, AIMessageChunk
from typer.testing import CliRunner

from app.cli import cli
from app.core.llm import service as llm_service
from app.core.settings import get_settings

runner = CliRunner()


def test_ac2_prints_prompt_completion_total_tokens_and_usd_cost(
    recording_chat_open_router, monkeypatch
):
    # ← AC2
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)
    recording_chat_open_router.response = AIMessage(
        content="A dazed creature can't take actions.",
        usage_metadata={"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        response_metadata={"cost": 0.001234},
    )

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])

    assert result.exit_code == 0, result.stderr
    assert "A dazed creature can't take actions." in result.stdout
    assert "tokens: prompt=12 completion=34 total=46 · cost: $0.001234" in result.stdout


def test_ac2_prints_cost_unavailable_when_absent_from_response_metadata(
    recording_chat_open_router, monkeypatch
):
    # ← AC2
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)
    recording_chat_open_router.response = AIMessage(
        content="A dazed creature can't take actions.",
        usage_metadata={"input_tokens": 5, "output_tokens": 7, "total_tokens": 12},
        response_metadata={},
    )

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])

    assert result.exit_code == 0, result.stderr
    assert "tokens: prompt=5 completion=7 total=12 · cost: unavailable" in result.stdout


def test_ac4_stream_prints_incrementally_and_emits_one_usage_line(
    recording_chat_open_router, monkeypatch
):
    # ← AC4
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)
    first = AIMessageChunk(content="A dazed creature ")
    second = AIMessageChunk(
        content="can't take actions.",
        usage_metadata={"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        response_metadata={"cost": 0.001234},
    )
    recording_chat_open_router.chunks = [first, second]
    # `.invoke()` must not be used on this path: leaving `response` unset
    # (None) means a wrong `.invoke()` call surfaces as a broken/empty
    # answer instead of silently passing.
    recording_chat_open_router.response = None

    result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--stream"])

    assert result.exit_code == 0, result.stderr
    # Both chunks' text reached stdout, in the order they were streamed.
    assert result.stdout.index("A dazed creature ") < result.stdout.index("can't take actions.")
    assert "A dazed creature can't take actions." in result.stdout
    # Exactly one usage line, built off the *accumulated* message: its
    # numbers are the second (last) chunk's, not the first, usage-less, one.
    usage_lines = [line for line in result.stdout.splitlines() if line.startswith("tokens: ")]
    assert usage_lines == ["tokens: prompt=12 completion=34 total=46 · cost: $0.001234"]


def test_ac5_blank_api_key_exits_1_names_the_variable_with_no_traceback(
    recording_chat_open_router, monkeypatch
):
    # ← AC5
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    try:
        result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition."])
    finally:
        # Settings is `@lru_cache`d process-wide: undo the blank-key read so
        # it cannot leak into a later test once `monkeypatch` restores the
        # env var (mirrors `tests/conftest.py`'s `production_client`).
        get_settings.cache_clear()

    assert result.exit_code == 1
    assert "OPENROUTER_API_KEY" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Traceback" not in result.stdout
    # Raised before constructing anything (I1).
    assert recording_chat_open_router.calls == []


# --- Sprint 02 AC4 -----------------------------------------------------
#
# `--details` must never leak the configured OpenRouter API key to the
# terminal. Unlike `test_commands_details.py` (WI4's own suite, which
# monkeypatches `llm_service.chat` directly and proves a *decoy* key never
# printed), this drives the real gateway boundary: a stub HTTP transport
# echoes the configured key back inside a raw (non-JSON) error body, which
# is the real leak path research.md calls out -- `OpenRouterDefaultError`
# inlines the raw response body into its own `.message`, and `classify()`
# must redact it before `--details` ever sees `provider_message`.

CANARY_API_KEY = "sk-or-v1-canary-leak-check-11223344556677889900"


def test_ac4_details_never_leaks_the_api_key_the_provider_echoes_back(monkeypatch):
    # ← AC4
    monkeypatch.setenv("OPENROUTER_API_KEY", CANARY_API_KEY)
    get_settings.cache_clear()

    def handler(request):
        # Non-JSON content type + an unmapped-by-specific-class status (500
        # is JSON-only in the SDK's dispatch table) forces the SDK's
        # fallback `OpenRouterDefaultError`, which inlines the raw body --
        # containing the canary key -- straight into `.message`.
        body = f"upstream rejected the request for key {CANARY_API_KEY}"
        return httpx.Response(500, content=body.encode(), headers={"content-type": "text/plain"})

    def fake_build_sdk_client(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", fake_build_sdk_client)

    try:
        result = runner.invoke(cli, ["llm", "chat", "Name one D&D condition.", "--details"])
    finally:
        get_settings.cache_clear()

    assert result.exit_code == 1
    combined = result.stdout + result.stderr
    assert CANARY_API_KEY not in combined
    assert "The AI service could not complete that request." in result.stderr
