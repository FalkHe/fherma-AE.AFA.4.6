"""QA independent verification of step 3.13 (advisor agent loop).

This file does not re-author the dev's `test_advisor.py` coverage (16 tests:
step-budget termination, tools-unbound final invoke, context rebuild, tool_calls
capture incl. failures, sources dedup/cap within one call, recommendation
enrichment incl. skip-unknown). It proves the acceptance criteria the dev suite
leaves untouched or only partially exercises, from fresh fixtures:

* tool calls within one round run **sequentially, in the order requested**, and
  their `ToolMessage`s are appended to the conversation in that same order;
* `asyncio.timeout` wraps the **whole turn** — a slow *tool* (not just a slow
  model call) trips it;
* the model factory is asked for `settings.advisor_model` specifically, proven
  by contrast against a differently-configured `settings.chat_model` (the 3.5
  QA precedent for this exact split);
* `sources[]` dedup/cap operates **across multiple `retrieve_bike_knowledge`
  calls in one turn**, not per-call, and every kept entry validates against the
  read-path `MessageSource` schema;
* `present_recommendations`: `imageUrl` is `null` when the model has no
  *approved* image, and the tool's acknowledgement string actually reaches the
  model as the `ToolMessage` content (not just the collector).

No test opens a database or reaches OpenRouter.
"""

import asyncio
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

from app.api.schemas.chat_messages import MessageSource
from app.core.config import get_settings
from app.db.models.chat import Chat
from app.db.models.motorbike import MotorbikeStatus
from app.db.models.motorbike_image import ImageStatus
from app.llm.agents import advisor
from app.services import (
    catalogue_search_service,
    chat_service,
    naming_service,
    product_service,
    rag_pipeline_service,
)
from app.services.catalogue_search_service import COMPARISON_SPEC_FIELDS, VerifiedSpecs
from app.services.naming_service import NameParts
from app.services.rag_pipeline_service import RagResult
from tests.services.conftest import FakeAsyncSession

BIKE_A = "01J0QABIKE00000000000AAAQ"
IMAGE_A = "01J0QAIMAGE0000000000AAAQ"


@dataclass
class _Recording:
    """One model call, for the tests that only care about the messages sent."""

    messages: list[BaseMessage]


class _Model:
    """A minimal scripted chat model: `bind_tools` returns the same object.

    Distinct from the dev suite's `ScriptedModel` (which marks tool-bound vs
    unbound calls) — these tests do not need that distinction, only the
    messages each call received and the ability to script answers.
    """

    def __init__(self, *answers: AIMessage) -> None:
        self.answers: deque[AIMessage] = deque(answers)
        self.calls: list[_Recording] = []
        self.bound: list[Any] | None = None

    def bind_tools(self, bound: Any) -> "_Model":
        self.bound = list(bound)
        return self

    async def ainvoke(self, messages: Any, **_kwargs: Any) -> AIMessage:
        self.calls.append(_Recording(list(messages)))
        if self.answers:
            return self.answers.popleft()
        return AIMessage("That will do for now.")


def _tool_call(name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"name": name, "args": arguments, "id": call_id, "type": "tool_call"}


class _Motorbike:
    def __init__(self, motorbike_id: str, name: str, status: MotorbikeStatus) -> None:
        self.id = motorbike_id
        self.query_name = name
        self.status = status


class _Image:
    def __init__(self, image_id: str, status: ImageStatus) -> None:
        self.id = image_id
        self.status = status


@pytest.fixture
def fake_session() -> FakeAsyncSession:
    return FakeAsyncSession()


@pytest.fixture
def services(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Stub the services every tool of this file reaches; nothing hits a DB."""

    @dataclass
    class _Recorder:
        by_name: dict[str, _Motorbike] = field(default_factory=dict)
        by_id: dict[str, _Motorbike] = field(default_factory=dict)
        images: dict[str, list[_Image]] = field(default_factory=dict)
        specs: list[VerifiedSpecs] = field(default_factory=list)
        rag_results: deque[RagResult] = field(default_factory=deque)
        retrieve_calls: list[str] = field(default_factory=list)
        retrieve_delay: dict[str, float] = field(default_factory=dict)

    recorder = _Recorder()

    async def resolve_name(session: Any, name: str) -> _Motorbike | None:
        return recorder.by_name.get(name)

    async def get_motorbike(session: Any, motorbike_id: str) -> _Motorbike | None:
        return recorder.by_id.get(motorbike_id)

    async def list_images(session: Any, *, motorbike_id: str | None = None) -> list[_Image]:
        return recorder.images.get(motorbike_id or "", [])

    async def get_verified_specs(session: Any, motorbike_ids: Any) -> list[VerifiedSpecs]:
        wanted = set(motorbike_ids)
        return [entry for entry in recorder.specs if entry.motorbike_id in wanted]

    async def retrieve(session: Any, utterance: str, **kwargs: Any) -> RagResult:
        recorder.retrieve_calls.append(f"start:{utterance}")
        delay = recorder.retrieve_delay.get(utterance, 0.0)
        if delay:
            await asyncio.sleep(delay)
        recorder.retrieve_calls.append(f"end:{utterance}")
        if recorder.rag_results:
            return recorder.rag_results.popleft()
        return RagResult(
            queries=[utterance], applied_filters={}, candidate_motorbike_ids=[], chunks=[]
        )

    async def load_name_parts(session: Any, motorbike_ids: Any) -> dict[str, NameParts]:
        found = {}
        for motorbike_id in motorbike_ids:
            motorbike = recorder.by_id.get(motorbike_id)
            if motorbike is not None:
                found[motorbike_id] = _parts(motorbike)
        return found

    monkeypatch.setattr(catalogue_search_service, "resolve_name", resolve_name)
    monkeypatch.setattr(product_service, "get_motorbike", get_motorbike)
    monkeypatch.setattr(product_service, "list_images", list_images)
    monkeypatch.setattr(catalogue_search_service, "get_verified_specs", get_verified_specs)
    monkeypatch.setattr(rag_pipeline_service, "retrieve", retrieve)
    monkeypatch.setattr(naming_service, "load_name_parts", load_name_parts)
    return recorder


def _parts(motorbike: _Motorbike) -> NameParts:
    """`NameParts` for a stubbed `_Motorbike`: no structured identity, so
    `render_name` falls back to `query_name` verbatim — this test file is not
    about naming.
    """
    return NameParts(
        motorbike_id=motorbike.id,
        manufacturer=None,
        buildingline=None,
        model_name=None,
        year_from=None,
        year_to=None,
        query_name=motorbike.query_name,
    )


def _approved(services: Any, name: str, motorbike_id: str, **values: Any) -> None:
    entry = _Motorbike(motorbike_id, name, MotorbikeStatus.APPROVED)
    services.by_name[name] = entry
    services.by_id[motorbike_id] = entry
    services.specs.append(
        VerifiedSpecs(
            motorbike_id=motorbike_id,
            name=name,
            values={field_name: values.get(field_name) for field_name in COMPARISON_SPEC_FIELDS},
            parts=_parts(entry),
        )
    )


def _chat(session: FakeAsyncSession) -> Chat:
    return asyncio.run(chat_service.create_chat(session, "0" * 22 + "USER"))


def _install_model(monkeypatch: pytest.MonkeyPatch, model: _Model) -> None:
    monkeypatch.setattr(advisor, "get_chat_model", lambda *_a, **_k: model, raising=True)


def _run(session: FakeAsyncSession, chat: Chat) -> advisor.AdvisorResult:
    return asyncio.run(advisor.run_advisor_turn(session, chat))


def _chunk(chunk_id: str, document_id: str, score: float) -> Any:
    from app.services.retrieval_service import RetrievedChunk

    return RetrievedChunk(
        chunk_id=chunk_id,
        motorbike_id=BIKE_A,
        text=f"Prose of {chunk_id}.",
        score=score,
        source_document_id=document_id,
        source_url=f"https://example.test/{document_id}",
        source_title=f"Document {document_id}",
        heading_path=None,
        page_number=None,
        sequence=1,
    )


# --- loop mechanics: sequential execution, ordered ToolMessages ---------------


def test_multiple_tool_calls_in_one_round_run_sequentially_in_request_order(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A slow first call must fully finish before the second one starts.

    If the loop ever switched to `asyncio.gather` this would show up as
    `start:second` landing before `end:first` in the recorded order.
    """
    services.retrieve_delay["first"] = 0.05
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[
                _tool_call("retrieve_bike_knowledge", {"query": "first"}, "call_1"),
                _tool_call("retrieve_bike_knowledge", {"query": "second"}, "call_2"),
            ],
        ),
        AIMessage("Here is what I found."),
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    result = _run(fake_session, chat)

    assert services.retrieve_calls == [
        "start:first",
        "end:first",
        "start:second",
        "end:second",
    ]
    assert len(result.tool_calls) == 2
    # The ToolMessages reach the second invoke in the same order as requested.
    tool_messages = [m for m in model.calls[1].messages if isinstance(m, ToolMessage)]
    assert [message.tool_call_id for message in tool_messages] == ["call_1", "call_2"]
    assert result.body == "Here is what I found."


# --- loop mechanics: the timeout wraps tool execution, not just the model -----


def test_timeout_wraps_a_slow_tool_not_only_a_slow_model_call(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tool that hangs must cancel the turn exactly like a hung model call.

    The model itself never sleeps here — only the service behind the tool
    does — so this fails if `asyncio.timeout` were scoped around the model
    calls alone instead of the whole `_loop`.
    """
    monkeypatch.setattr(get_settings(), "agent_timeout_seconds", 0.05)
    services.retrieve_delay["slow"] = 1.0
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[_tool_call("retrieve_bike_knowledge", {"query": "slow"}, "call_1")],
        )
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    with pytest.raises(TimeoutError):
        _run(fake_session, chat)


# --- context rebuild: advisor_model, contrasted against chat_model ------------


def test_the_loop_requests_the_advisor_model_not_the_chat_model(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The 3.5 model split, proven at the 3.13 call site: never `CHAT_MODEL`."""
    settings = get_settings()
    monkeypatch.setattr(settings, "advisor_model", "openai/advisor-sentinel")
    monkeypatch.setattr(settings, "chat_model", "openai/chat-sentinel")
    requested: list[str | None] = []
    model = _Model(AIMessage("Hello."))

    def factory(name: str | None = None) -> _Model:
        requested.append(name)
        return model

    monkeypatch.setattr(advisor, "get_chat_model", factory)
    chat = _chat(fake_session)

    _run(fake_session, chat)

    assert requested == ["openai/advisor-sentinel"]
    assert "openai/chat-sentinel" not in requested


# --- sources: dedup/cap across MULTIPLE retrieve calls in one turn ------------


def test_sources_dedupe_across_separate_retrieve_calls_not_only_within_one(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same document cited by two different calls is still one entry.

    The dev suite's dedup test puts the duplicate pair inside a single
    `RagResult` (one call); this proves the collector-level rule holds when
    the duplicate spans two separate `retrieve_bike_knowledge` invocations —
    the actual multi-call scenario the acceptance criterion names.
    """
    monkeypatch.setattr(get_settings(), "agent_max_tool_steps", 3)
    services.rag_results.extend(
        [
            RagResult(
                queries=["first"],
                applied_filters={},
                candidate_motorbike_ids=[BIKE_A],
                chunks=[_chunk("chunk-weak", "doc-shared", 0.010)],
            ),
            RagResult(
                queries=["second"],
                applied_filters={},
                candidate_motorbike_ids=[BIKE_A],
                chunks=[_chunk("chunk-strong", "doc-shared", 0.040)],
            ),
        ]
    )
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[_tool_call("retrieve_bike_knowledge", {"query": "first"}, "call_1")],
        ),
        AIMessage(
            content="",
            tool_calls=[_tool_call("retrieve_bike_knowledge", {"query": "second"}, "call_2")],
        ),
        AIMessage("Reviewers agree it is forgiving."),
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    result = _run(fake_session, chat)

    (source,) = result.sources
    assert source["sourceDocumentId"] == "doc-shared"
    # The best score across both calls survives, not the first or last seen.
    assert source["chunkId"] == "chunk-strong"
    assert source["score"] == pytest.approx(0.040)
    # Validates against the exact read-path schema the API serves.
    validated = MessageSource.model_validate(source)
    assert validated.chunk_id == "chunk-strong"


def test_every_source_kept_validates_against_the_read_path_schema(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every entry the collector keeps must round-trip through `MessageSource`."""
    services.rag_results.append(
        RagResult(
            queries=["q"],
            applied_filters={"category": ["naked"]},
            candidate_motorbike_ids=[BIKE_A],
            chunks=[_chunk(f"chunk-{i}", f"doc-{i}", 0.01 * i) for i in range(1, 4)],
        )
    )
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[_tool_call("retrieve_bike_knowledge", {"query": "q"}, "call_1")],
        ),
        AIMessage("Here is what reviewers say."),
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    result = _run(fake_session, chat)

    assert len(result.sources) == 3
    for source in result.sources:
        MessageSource.model_validate(source)


# --- present_recommendations: imageUrl null, and the ack reaches the model ----


def test_recommendation_image_url_is_null_without_an_approved_image(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A model with only a pending image (or none at all) gets a normal card."""
    _approved(services, "Honda CB500F", BIKE_A, category="naked")
    services.images[BIKE_A] = [_Image("01J0QAIMAGEPEND0000000AAA", ImageStatus.PENDING)]
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "present_recommendations",
                    {
                        "recommendations": [
                            {"motorbikeName": "Honda CB500F", "rationale": "A solid start."}
                        ]
                    },
                    "call_1",
                )
            ],
        ),
        AIMessage("Here is one to consider."),
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    result = _run(fake_session, chat)

    (snapshot,) = result.recommendations
    assert snapshot["imageUrl"] is None
    from app.api.schemas.chat_messages import Recommendation

    Recommendation.model_validate(snapshot)


def test_present_recommendations_returns_an_ack_string_the_model_reads(
    fake_session: FakeAsyncSession, services: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tool's `ToolMessage` content is the acknowledgement, not the snapshot."""
    _approved(services, "Honda CB500F", BIKE_A, category="naked")
    model = _Model(
        AIMessage(
            content="",
            tool_calls=[
                _tool_call(
                    "present_recommendations",
                    {
                        "recommendations": [
                            {"motorbikeName": "Honda CB500F", "rationale": "Fits your budget."}
                        ]
                    },
                    "call_1",
                )
            ],
        ),
        AIMessage("Take a look at this one."),
    )
    _install_model(monkeypatch, model)
    chat = _chat(fake_session)

    _run(fake_session, chat)

    (tool_message,) = [m for m in model.calls[1].messages if isinstance(m, ToolMessage)]
    content = str(tool_message.content)
    assert "Honda CB500F" in content
    # The ack, not the enriched snapshot: no key-spec numbers leak into the model's copy.
    assert "keySpecs" not in content
    assert "presented" in content and "message" in content
