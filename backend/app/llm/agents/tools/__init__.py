"""The advisor's tool convention: one shape every tool of steps 3.11–3.14 follows.

A tool is four things, and nothing else:

1. **A Pydantic args schema with camelCase aliases.** Its JSON schema is what the
   model is shown, and the model itself is the only validation of what comes back
   — an argument the schema rejects never reaches a service. (`_langchain_tool`
   explains why the *schema*, not the class, is handed to LangChain.)
2. **A coroutine `run(ctx, args)` that calls services.** *No SQL in a tool*
   (`agent tool → application service → database`, the architecture's rule): a
   tool composes service calls, maps their read models into a result and decides
   nothing about storage. Tool calls run **sequentially** over the one session of
   the job that owns the turn, because one `AsyncSession` cannot serve concurrent
   statements.
3. **A JSON-serializable Pydantic result in the pinned shape.**
   `docs/roadmap/stage-01/phase-3/shared-knowledge.md` §Tool result schemas is frozen —
   the chat UI's renderers are written against those exact camelCase keys, so a
   renamed field breaks the other track silently. A tool that cannot resolve a
   bike name returns the shared `UnknownBikeResult` instead of its normal result;
   nothing here raises for a name the catalogue does not know.
4. **A registry entry** (`ToolSpec`), so `build_advisor_tools(ctx)` can hand the
   loop a list of LangChain tools and `app tools run` can invoke exactly the same
   code path from the command line.

`ToolContext` carries what a tool may touch: the session, the chat whose turn is
being answered (write tools need it; `None` in the CLI harness) and the
`ToolCallCollector`. **Recording is the wrapper's job, not the tool's** —
`execute` records every call it runs into the pinned `tool_calls[]` shape,
successes and failures alike, so no tool can forget to be visible. The step-3.13
loop appends `execute`'s **return value** to the conversation as a `ToolMessage`
and persists `collector.tool_calls` with the assistant message; a failure is
recorded and then re-raised, so the loop still gets to tell the model what went
wrong.

**Step 5.8:** what is recorded and what is returned are no longer guaranteed to
be the same object. `execute` always records the unfenced `result.model_dump(...)`
— `tool_calls[].result` and `sources[]` stay byte-identical to before 5.8 — but
returns `spec.model_view(result)` instead when the tool declares one. Only
`retrieve_bike_knowledge.TOOL` does, to fence retrieved chunk text for the model
without fencing the persisted/UI copy. Every other tool is unaffected: no
`model_view` means the recorded and returned payloads are identical, exactly as
before.

Argument validation failures are the one thing *not* recorded here: a call whose
arguments never validated never executed, and the loop reports it to the model as
the error it is.
"""

import json
import logging
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import new_ulid
from app.db.models.chat import Chat
from app.db.models.motorbike import Motorbike, MotorbikeStatus
from app.services import catalogue_search_service, product_service

logger = logging.getLogger(__name__)

# The two `tool_calls[].status` values of the frozen persisted shape (validated on
# read by `app.api.schemas.chat_messages.ToolCall`; kept as plain strings here so
# the LLM layer does not import the API layer).
SUCCEEDED = "succeeded"
FAILED = "failed"

# How much of a failed call's error reaches the recorded entry: one line, not a
# gateway response body (the `rag_pipeline_service` cap, same reason).
MAX_ERROR_CHARS = 200

# How many `sources[]` entries one assistant message carries (the pinned cap):
# the collapsible source list is provenance for an answer, not a bibliography,
# and a turn that retrieved four times would otherwise cite forty documents.
MAX_SOURCES = 8


class ToolModel(BaseModel):
    """Base for every tool's args and result models: camelCase out, snake in.

    The same rule as the API layer's `JsonApiModel`, for the same reason — these
    shapes are read by the SPA — but deliberately a separate base: a tool schema
    is not a wire resource, and the LLM layer does not depend on the API layer.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UnknownBikeResult(ToolModel):
    """The shared answer to "I cannot find that bike".

    Pinned shape: `{"unknownBike": "<name as given>"}`. Every tool that takes a
    bike may answer with it instead of its normal result, and step 3.14 turns
    repeated mentions into an admin backlog flag — which is why the name is
    echoed verbatim rather than normalized.
    """

    unknown_bike: str


@dataclass(slots=True)
class ToolCallCollector:
    """Per-turn capture of everything the tools did.

    Lives for one agent run and holds all three persisted traces of the
    assistant message, each already in its pinned camelCase shape:

    * `tool_calls` — every executed call, successes and failures alike;
    * the **sources**, contributed by `retrieve_bike_knowledge` and read back
      through `sources()`, which owns the pinned dedupe/order/cap;
    * the **recommendations**, contributed by `present_recommendations` and read
      back through `recommendations()`.

    The two read-back methods exist because both lists have rules the writer
    must not have to know: sources are deduplicated by `sourceDocumentId`
    keeping the best score, and a bike recommended twice in one turn is one
    card. `tool_calls` needs no such rule — a call executed twice happened
    twice.
    """

    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    # Keyed by `sourceDocumentId`: one entry per cited document, the
    # best-scoring chunk of it.
    _sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    # Keyed by `motorbikeId`, in insertion order: the advisor's own presentation
    # order is the card order.
    _recommendations: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, tool: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        """Record a call that returned a result."""
        self.tool_calls.append(
            {
                # A ULID, which the pinned shape allows next to a provider call
                # id: the wrapper is what runs the call, and it never sees the
                # provider's id.
                "id": new_ulid(),
                "tool": tool,
                "arguments": arguments,
                "result": result,
                "status": SUCCEEDED,
                "error": None,
            }
        )

    def record_failure(self, tool: str, arguments: dict[str, Any], error: Exception) -> None:
        """Record a call that raised, keeping every key of the pinned shape.

        `result` stays an empty object rather than being omitted: the read path
        validates the stored entry against the frozen `ToolCall` model, and a
        missing key there is a 500 on `GET /api/chat-messages`.
        """
        self.tool_calls.append(
            {
                "id": new_ulid(),
                "tool": tool,
                "arguments": arguments,
                "result": {},
                "status": FAILED,
                "error": f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS],
            }
        )

    def record_sources(self, sources: Iterable[dict[str, Any]]) -> None:
        """Add cited chunks to the turn, keeping the best one per document.

        `sources` are already in the pinned `sources[]` shape. Two chunks of the
        same source document are one citation: the customer is shown *where* an
        answer comes from, and the same brochure listed twice says nothing more
        than once. The higher score wins, because that is the chunk the answer
        most likely rests on.
        """
        for source in sources:
            key = source["sourceDocumentId"]
            best = self._sources.get(key)
            if best is None or source["score"] > best["score"]:
                self._sources[key] = source

    def sources(self) -> list[dict[str, Any]]:
        """Return the cited sources in the pinned order, capped at `MAX_SOURCES`.

        Score descending, `chunkId` as the tiebreaker so the list is stable for
        equal scores (the retrieval services' tiebreaker, for the same reason).
        """
        ordered = sorted(
            self._sources.values(), key=lambda source: (-source["score"], source["chunkId"])
        )
        return ordered[:MAX_SOURCES]

    def record_recommendations(self, recommendations: Iterable[dict[str, Any]]) -> None:
        """Add recommendation snapshots to the turn, one card per model.

        Already in the pinned `recommendations[]` shape. The **first** snapshot
        of a bike wins: a second `present_recommendations` call naming it again
        is the same card, and the rationale the advisor gave first is the one the
        prose around it explains.
        """
        for recommendation in recommendations:
            self._recommendations.setdefault(recommendation["motorbikeId"], recommendation)

    def recommendations(self) -> list[dict[str, Any]]:
        """Return the recommendation snapshots in presentation order."""
        return list(self._recommendations.values())


@dataclass(slots=True)
class ToolContext:
    """What a tool is allowed to touch during one turn.

    Attributes:
        session: The turn's one session. Tools read through services and never
            commit; the write tools of 3.13/3.14 commit inside their service.
        chat: The consultation being answered, for the tools that write
            chat-scoped rows. `None` when there is no chat (the `app tools run`
            harness), so a write tool must check it.
        collector: The per-turn capture. Defaulted, so a harness needs one
            argument.
    """

    session: AsyncSession
    chat: Chat | None = None
    collector: ToolCallCollector = field(default_factory=ToolCallCollector)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One registered tool: what the model sees and what runs.

    `description` is what the model reads to decide whether to call the tool. It
    stays in the tool module (a docstring-like constant, not a prompt template):
    it is part of the function schema LangChain sends, not a rendered prompt.

    `model_view` is the step-5.8 escape hatch for a tool whose result embeds
    untrusted prose: when set, `execute` still records the **unfenced** result as
    today (`tool_calls[].result` and `sources[]` stay byte-identical) but returns
    `model_view(result)` instead of the plain dump — the value that actually
    reaches the `ToolMessage` the model reads. `None` (the default, every tool but
    `retrieve_bike_knowledge`) means no split: the recorded and the model-facing
    payload are the same object, exactly as before 5.8.
    """

    name: str
    description: str
    args_schema: type[BaseModel]
    run: Callable[[ToolContext, Any], Awaitable[BaseModel]]
    model_view: Callable[[BaseModel], dict[str, Any]] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedBikes:
    """The outcome of resolving a tool's bike references.

    `unresolved` holds the **first** reference that resolved to nothing, exactly
    as it was given; the tool turns it into `UnknownBikeResult` and stops. Ids
    resolve before names, and duplicates are dropped — a customer naming the same
    bike twice gets one column, not two.
    """

    bikes: list[Motorbike]
    unresolved: str | None


def tool_specs() -> tuple[ToolSpec, ...]:
    """Return the registered tools, in a stable order.

    The imports are in-function on purpose (the enqueue-seam precedent): the tool
    modules import this convention module, so importing them at the top would be
    a cycle. The tuple is complete at eight (the pinned tool set); the registry
    order is the order the model sees the tools in — the reading order of a
    consultation: find candidates, compare them, check them against the customer,
    cost them, read what has been written about them, note what was learned and
    what the catalogue is missing, and finally put the cards on the table.
    """
    from app.llm.agents.tools import (
        catalogue_search,
        cost_estimator,
        flag_unknown_bike,
        licence_fit_check,
        present_recommendations,
        record_preference,
        retrieve_bike_knowledge,
        spec_comparison,
    )

    return (
        catalogue_search.TOOL,
        spec_comparison.TOOL,
        licence_fit_check.TOOL,
        cost_estimator.TOOL,
        retrieve_bike_knowledge.TOOL,
        record_preference.TOOL,
        flag_unknown_bike.TOOL,
        present_recommendations.TOOL,
    )


def tool_names() -> list[str]:
    """Return the registered tool names, for the CLI harness and its errors."""
    return [spec.name for spec in tool_specs()]


def get_tool_spec(name: str) -> ToolSpec:
    """Return the registered tool called `name`.

    Raises:
        KeyError: no tool is registered under that name (the CLI turns it into a
            message listing the ones that are).
    """
    for spec in tool_specs():
        if spec.name == name:
            return spec
    raise KeyError(name)


def build_advisor_tools(ctx: ToolContext) -> list[BaseTool]:
    """Return the advisor's tools, bound to one turn's context.

    Every tool is async-only (`coroutine=`): the whole request path is async, and
    a synchronous call would open a second session behind the loop's back.
    """
    return [_langchain_tool(spec, ctx) for spec in tool_specs()]


async def execute(spec: ToolSpec, ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate, run and record one tool call; return what the caller should send.

    The single execution path: `build_advisor_tools` wraps it for the agent loop
    and `app tools run` calls it directly, so the harness proves the same code the
    advisor runs.

    Args:
        spec: The registered tool.
        ctx: The turn's context (session, chat, collector).
        arguments: The raw arguments, camelCase or snake_case (the schemas accept
            both), as the model sent them.

    Returns:
        The result model dumped by alias — **always** what is recorded into
        `tool_calls[].result` and reaches the UI's renderer. When `spec.model_view`
        is set (step 5.8's escape hatch, currently only
        `retrieve_bike_knowledge.TOOL`), the *returned* value is
        `spec.model_view(result)` instead — the model-facing view of the same
        result, which may differ from what was recorded (a fenced snippet text,
        for example). The persisted/UI payload and `sources[]` are built from the
        unfenced `result` in both cases; only the caller's copy — the one that
        becomes the `ToolMessage` the model reads — can differ. `app tools run`
        therefore prints the model view for that one tool, not the recorded one;
        this is the harness showing what the model sees, not a pinned wire shape.

    Raises:
        pydantic.ValidationError: the arguments do not satisfy the args schema.
            Nothing ran, so nothing is recorded.
        Exception: whatever the services raise. The failure is recorded first
            (the turn must show it) and then re-raised for the caller to report.
    """
    args = spec.args_schema.model_validate(arguments)
    recorded_arguments = args.model_dump(by_alias=True)
    try:
        result = await spec.run(ctx, args)
    except Exception as error:
        logger.warning("Tool %s failed: %s", spec.name, error, exc_info=error)
        ctx.collector.record_failure(spec.name, recorded_arguments, error)
        raise

    payload = result.model_dump(by_alias=True)
    ctx.collector.record(spec.name, recorded_arguments, payload)
    return spec.model_view(result) if spec.model_view is not None else payload


async def resolve_references(
    ctx: ToolContext,
    *,
    motorbike_ids: Sequence[str] = (),
    names: Sequence[str] = (),
) -> ResolvedBikes:
    """Resolve a tool's bike references to approved catalogue entries.

    Ids are looked up directly (and must be approved, like any other reference);
    names go through `catalogue_search_service.resolve_name` (exact slug, then
    type code, then substring). The first reference that resolves to nothing
    stops the walk — the tool answers `{"unknownBike": …}` and there is no
    point in loading the rest.

    Args:
        ctx: The turn's context; only its session is used.
        motorbike_ids: Catalogue ids, resolved before the names.
        names: Model names as they were written.
    """
    bikes: list[Motorbike] = []
    seen: set[str] = set()

    for reference in list(motorbike_ids):
        motorbike = await product_service.get_motorbike(ctx.session, reference)
        if motorbike is None or motorbike.status is not MotorbikeStatus.APPROVED:
            logger.info("Tool reference %r is not an approved catalogue id.", reference)
            return ResolvedBikes(bikes=bikes, unresolved=reference)
        if motorbike.id not in seen:
            seen.add(motorbike.id)
            bikes.append(motorbike)

    for reference in list(names):
        motorbike = await catalogue_search_service.resolve_name(ctx.session, reference)
        if motorbike is None:
            logger.info("Tool reference %r did not resolve to an approved model.", reference)
            return ResolvedBikes(bikes=bikes, unresolved=reference)
        if motorbike.id not in seen:
            seen.add(motorbike.id)
            bikes.append(motorbike)

    return ResolvedBikes(bikes=bikes, unresolved=None)


def _langchain_tool(spec: ToolSpec, ctx: ToolContext) -> BaseTool:
    """Wrap one `ToolSpec` as the LangChain tool the model is bound to.

    Two library details decide the shape of this function:

    * **The args schema is passed as a JSON-schema dict, not as the model.**
      Given a Pydantic `args_schema`, `BaseTool.tool_call_schema` rebuilds a
      *subset model* from the annotations — which drops `model_config` and any
      `model_json_schema` override, so the model would be shown snake_case
      properties and the camelCase convention would exist only on paper (verified
      against the installed langchain-core). A dict schema is forwarded verbatim,
      so what the provider sees is exactly what the schema says. Validation is not
      lost: `execute` validates with the model itself, which is the single
      boundary either way (and the one the CLI harness goes through too).
    * **The coroutine returns the result as a JSON string.** That string becomes
      the `ToolMessage` content the model reads next, and `str(dict)` would hand
      it Python syntax (`None`, `True`) instead of JSON. The structured payload is
      not lost — it is already in the collector.
    """

    async def call(**arguments: Any) -> str:
        payload = await execute(spec, ctx, arguments)
        return json.dumps(payload, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=call,
        name=spec.name,
        description=spec.description,
        args_schema=spec.args_schema.model_json_schema(),
    )
