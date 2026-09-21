"""What the LLM seam sends to Langfuse.

Black-box through `service.chat()` / `chat_stream()` / `embed_texts()` /
`generate_image()`, with two seams stubbed and nothing else: the OpenRouter
gateway (`service.build_sdk_client`, as every other file in this directory
does) and the Langfuse client (`tracing._client`, a `FakeLangfuse` - see
`tests/core/tracing/conftest.py`). No credentials, no sockets.

The trace shape being pinned here, per Langfuse's own best-practice
guidance:

- One root observation per entry point, named verb-first with no dynamic
  values in the name - names are what evaluators, dashboards and saved
  filters target, so they are an API and a test is what keeps them stable.
- The root opens *outside* the retry loop, so a call that is retried three
  times is one trace with three child observations, not three traces.
- The most specific observation type wins: `embedding` for an embedding
  call, `generation` for an image, and for chat the LangChain
  `CallbackHandler` (carried in `config=`) rather than anything this app
  builds by hand.
- Model, token usage and USD cost ride on the observation, because that is
  what makes Langfuse able to price and compare model calls at all.
"""

import base64

import httpx
import openrouter
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk

from app.core.llm import service as llm_service
from app.core.llm.errors import LlmUnavailableError
from app.core.tracing import service as tracing
from tests.core.tracing.conftest import FakeLangfuse

_PNG_BYTES = b"\x89PNG\r\n\x1a\nnot-a-real-png-but-good-enough"
_PNG_B64 = base64.b64encode(_PNG_BYTES).decode("ascii")


@pytest.fixture
def traced(monkeypatch):
    """Tracing on, against a fake Langfuse client. Yields the client, whose
    `.observations` is the trace tree this file asserts against."""
    client = FakeLangfuse()
    monkeypatch.setattr(tracing, "_client", client)
    return client


def _stub_gateway(monkeypatch, handler):
    def _build(api_key):
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)


def _embeddings_handler(monkeypatch, *, usage=None, calls=None):
    def handler(request):
        if calls is not None:
            calls.append(request)
        body = {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4], "object": "embedding", "index": 0}],
            "model": "test/embedding-model",
            "object": "list",
        }
        if usage is not None:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    _stub_gateway(monkeypatch, handler)


def _image_handler(monkeypatch, *, usage=None):
    def handler(request):
        body = {"created": 0, "data": [{"b64_json": _PNG_B64, "media_type": "image/png"}]}
        if usage is not None:
            body["usage"] = usage
        return httpx.Response(200, json=body)

    _stub_gateway(monkeypatch, handler)


# --------------------------------------------------------------------------
# chat / chat_stream
# --------------------------------------------------------------------------


def test_chat_hands_langchain_its_run_name_and_callbacks(
    monkeypatch, traced, recording_chat_open_router
):
    recording_chat_open_router.calls = []
    recording_chat_open_router.configs = []
    recording_chat_open_router.response = AIMessage(content="A goblin appears.")
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)
    handlers = []

    class _FakeHandler:
        def __init__(self):
            handlers.append(self)

    monkeypatch.setattr(tracing, "CallbackHandler", _FakeHandler)

    llm_service.chat("What happens?")

    config = recording_chat_open_router.configs[0]
    assert config["run_name"] == "invoke-chat-model"
    # The integration's handler, not a hand-rolled generation: it is what
    # captures model, tokens and cost without this app computing any of it.
    assert config["callbacks"] == handlers


def test_chat_opens_one_root_span_carrying_the_prompt_and_the_reply(
    monkeypatch, traced, recording_chat_open_router
):
    recording_chat_open_router.calls = []
    recording_chat_open_router.configs = []
    recording_chat_open_router.response = AIMessage(content="A goblin appears.")
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    llm_service.chat("What happens?")

    (root,) = traced.observations
    assert root.name == "generate-chat-reply"
    assert root.as_type == "span"
    assert root.attributes["input"] == "What happens?"
    assert root.updates == [{"output": "A goblin appears."}]
    assert root.closed is True


def test_chat_stream_keeps_its_root_span_open_until_the_last_chunk(
    monkeypatch, traced, recording_chat_open_router
):
    recording_chat_open_router.calls = []
    recording_chat_open_router.configs = []
    recording_chat_open_router.chunks = [
        AIMessageChunk(content="A gob"),
        AIMessageChunk(content="lin appears."),
    ]
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    stream = llm_service.chat_stream("What happens?")
    first = next(stream)

    # Mid-stream: the span is open, so anything the caller does while
    # consuming still lands inside this trace.
    (root,) = traced.observations
    assert first.text == "A gob"
    assert root.closed is False

    rest = list(stream)

    assert [chunk.text for chunk in rest] == ["lin appears."]
    assert root.name == "stream-chat-reply"
    # The accumulated text, not the last chunk: the root observation's
    # output is what the tracing table shows and what evaluators read.
    assert root.updates == [{"output": "A goblin appears."}]
    assert root.closed is True
    assert recording_chat_open_router.configs[0]["run_name"] == "stream-chat-model"


def test_chat_traces_nothing_and_still_answers_with_tracing_off(
    monkeypatch, recording_chat_open_router
):
    recording_chat_open_router.calls = []
    recording_chat_open_router.configs = []
    recording_chat_open_router.response = AIMessage(content="A goblin appears.")
    monkeypatch.setattr(llm_service, "ChatOpenRouter", recording_chat_open_router)

    message = llm_service.chat("What happens?")

    assert message.text == "A goblin appears."
    assert recording_chat_open_router.configs[0] == {"run_name": "invoke-chat-model"}


# --------------------------------------------------------------------------
# embed_texts
# --------------------------------------------------------------------------


def test_embed_texts_records_an_embedding_observation_with_model_usage_and_cost(
    monkeypatch, traced
):
    _embeddings_handler(
        monkeypatch, usage={"prompt_tokens": 7, "total_tokens": 7, "cost": 0.000002}
    )

    llm_service.embed_texts(["the goblin attacks"])

    root, child = traced.observations
    assert root.name == "embed-texts"
    assert root.attributes["input"] == {"textCount": 1}

    assert child.name == "create-embeddings"
    # `embedding`, not a generic span: the type is what lets Langfuse
    # price the call and what evaluators and dashboards filter on.
    assert child.as_type == "embedding"
    assert child.attributes["model"] == "test/embedding-model"
    assert child.attributes["input"] == ["the goblin attacks"]

    (update,) = child.updates
    # The shape, never the 1536 floats: they make the observation
    # unreadable and say nothing the shape does not.
    assert update["output"] == {"vectorCount": 1, "dimensions": 4}
    assert update["usage_details"] == {"input": 7, "output": 0, "total": 7}
    assert update["cost_details"] == {"total": 0.000002}


def test_embed_texts_omits_cost_details_when_the_provider_reports_no_cost(monkeypatch, traced):
    _embeddings_handler(monkeypatch, usage={"prompt_tokens": 7, "total_tokens": 7})

    llm_service.embed_texts(["the goblin attacks"])

    (update,) = traced.observations[1].updates
    # Omitted rather than zero: a zero would read as "this call was free"
    # and would override Langfuse's own model pricing.
    assert "cost_details" not in update


def test_a_retried_call_is_one_trace_with_one_child_per_attempt(monkeypatch, traced):
    attempts = {"count": 0}

    def _build(api_key):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise LlmUnavailableError()
        return openrouter.OpenRouter(
            api_key=api_key,
            client=httpx.Client(
                transport=httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        json={
                            "data": [
                                {
                                    "embedding": [0.1, 0.2, 0.3, 0.4],
                                    "object": "embedding",
                                    "index": 0,
                                }
                            ],
                            "model": "test/embedding-model",
                            "object": "list",
                        },
                    )
                )
            ),
            retry_config=None,
        )

    monkeypatch.setattr(llm_service, "build_sdk_client", _build)

    llm_service.embed_texts(["the goblin attacks"])

    # One root span, three children: the retry count is readable straight
    # off the trace tree, which is the whole reason the root opens outside
    # the retry loop.
    root, *children = traced.observations
    assert root.name == "embed-texts"
    assert [child.name for child in children] == ["create-embeddings"] * 3


# --------------------------------------------------------------------------
# generate_image
# --------------------------------------------------------------------------


def test_generate_image_records_a_generation_with_the_image_as_media(monkeypatch, traced):
    _image_handler(
        monkeypatch,
        usage={"prompt_tokens": 11, "completion_tokens": 2, "total_tokens": 13, "cost": 0.067},
    )

    llm_service.generate_image("a stoic half-orc ranger")

    root, child = traced.observations
    assert root.name == "generate-image"
    assert root.attributes["input"] == "a stoic half-orc ranger"

    assert child.name == "create-image"
    assert child.as_type == "generation"
    assert child.attributes["model"] == "test/image-model"
    assert child.attributes["metadata"] == {"url": "https://openrouter.ai/api/v1/images"}

    (update,) = child.updates
    # Wrapped as media so Langfuse uploads the bytes once and renders the
    # portrait inline, instead of the observation carrying base64 text.
    assert isinstance(update["output"], tracing.LangfuseMedia)
    assert update["usage_details"] == {"input": 11, "output": 2, "total": 13}
    assert update["cost_details"] == {"total": 0.067}


def test_generate_image_still_returns_the_image_with_tracing_off(monkeypatch):
    _image_handler(monkeypatch)

    result = llm_service.generate_image("a stoic half-orc ranger")

    assert result.image_bytes == _PNG_BYTES
    assert tracing.enabled() is False
