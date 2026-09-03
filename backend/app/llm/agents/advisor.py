"""The advisor's agent loop: one consultation turn, hand-rolled.

This is the centre of the product — the place where the interview, the catalogue,
the knowledge base and the customer's own words meet. It is deliberately a plain
loop over `bind_tools`, not a framework:

* **No graph, no prebuilt executor, no checkpointer.** Resumability in this
  application is *persistence*: every turn rebuilds its context from the stored
  timeline, so a killed worker, a second worker or a reload mid-answer all see
  the same conversation. A checkpointer would add a second source of truth for
  the same state (architecture decision, pinned in shared-knowledge).
* **The context is the stored timeline, body only.** Past tool traffic is not
  replayed: it is bookkeeping the customer can see, not something the model has
  to re-read, and replaying it would grow every turn by the size of all previous
  retrievals. What *is* carried across turns are the captured preferences, which
  the system prompt renders as a structured block.
* **Two budgets, both enforced here.** `AGENT_MAX_TOOL_STEPS` rounds of tool
  calls, then one final invoke with the tools unbound — a model that keeps
  reaching for tools still has to produce an answer. `AGENT_TIMEOUT_SECONDS`
  wraps the whole turn; exceeding it cancels the loop, and the job turns that
  into the apologetic message plus a `failed` operation. A consultation never
  hangs in the typing state because of this loop.
* **Nothing here writes to the database.** `run_advisor_turn` returns an
  `AdvisorResult`; `chat_response_service` persists it in one place, through
  `chat_service.append_assistant_message`. Tools may write (the explicitly
  permitted low-risk writes), and they do it inside their own service.

Tool failures are part of a normal turn: `tools.execute` records every executed
call — successes and failures alike — and re-raises, and this loop turns the
exception into an error `ToolMessage` so the model can say what went wrong or try
something else. A tool the model invented is answered the same way. The one thing
that ends the turn is the model producing no text at all, which the responder
rejects.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.runnables import Runnable
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.chat import Chat, ChatMessage, ChatMessageRole, ChatPreference
from app.llm.agents import tools
from app.llm.fencing import FENCE_END, FENCE_START, fence
from app.llm.models import get_chat_model
from app.llm.prompts import render_prompt
from app.services import chat_service

logger = logging.getLogger(__name__)

# The advisor's persona, domain, interview and refusal rules. Rendered with
# `is_opening` (empty timeline) and the active-preference block.
SYSTEM_PROMPT = "advisor_system"

# What the model is told when its tool budget is spent. A system instruction, not
# a fabricated customer message: it comes from the application, and the
# conversation must not look as if the customer had asked for a summary.
WRAP_UP_INSTRUCTION = (
    "You have used up the tool calls available for this turn. Answer the customer "
    "now with what you already know, name anything you could not check, and ask "
    "your next question — do not announce further lookups."
)

# How much of a failed tool call's error the model is shown (the collector's cap,
# same reason: a gateway body is not a message).
MAX_ERROR_CHARS = tools.MAX_ERROR_CHARS


@dataclass(frozen=True, slots=True)
class AdvisorResult:
    """One finished turn, ready to be persisted.

    The three traces are already in the pinned camelCase shapes of the
    `chat_messages` JSONB columns, so the responder stores them verbatim.
    """

    body: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    recommendations: list[dict[str, Any]] = field(default_factory=list)


async def run_advisor_turn(
    session: AsyncSession, chat: Chat, *, model: BaseChatModel | None = None
) -> AdvisorResult:
    """Answer the current turn of `chat` with the tool-calling advisor.

    Args:
        session: The turn's one session. Every read (timeline, preferences, the
            tools' service calls) goes through it, and the tool calls run
            **sequentially** because one `AsyncSession` cannot serve concurrent
            statements. Nothing is committed here.
        chat: The consultation being answered; its stored timeline and its active
            preferences are the whole context.
        model: Override for the chat model, for tests and harnesses. Production
            passes nothing and gets `get_chat_model(settings.advisor_model)` —
            the advisor's own configured model, never `CHAT_MODEL` and never a
            hardcoded id.

    Returns:
        The answer text plus the turn's tool calls, sources and recommendation
        snapshots. `body` may be empty when the model produced no text; the
        caller decides what that means.

    Raises:
        TimeoutError: the turn exceeded `AGENT_TIMEOUT_SECONDS`. The job turns it
            into the apologetic message and a `failed` operation.
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured.
        Exception: whatever the gateway raises. Tool failures are *not* raised —
            they are recorded and reported to the model.
    """
    settings = get_settings()
    history = await chat_service.list_messages(session, chat.id)
    preferences = await chat_service.active_preferences(session, chat.id)

    collector = tools.ToolCallCollector()
    ctx = tools.ToolContext(session=session, chat=chat, collector=collector)
    plain_model = model if model is not None else get_chat_model(settings.advisor_model)
    bound_model = plain_model.bind_tools(tools.build_advisor_tools(ctx))

    messages = build_context(history, preferences)
    logger.info(
        "chat %s: agent turn over %d stored message(s) and %d active preference(s).",
        chat.id,
        len(history),
        len(preferences),
    )

    async with asyncio.timeout(settings.agent_timeout_seconds):
        answer = await _loop(
            bound_model, plain_model, messages, ctx, max_steps=settings.agent_max_tool_steps
        )

    return AdvisorResult(
        body=answer.text.strip(),
        tool_calls=collector.tool_calls,
        sources=collector.sources(),
        recommendations=collector.recommendations(),
    )


def build_context(
    history: list[ChatMessage], preferences: list[ChatPreference]
) -> list[BaseMessage]:
    """Turn the stored state into the messages the first model call receives.

    The system prompt (with the active-preference block and the greeting switch)
    followed by the full timeline as Human/AI messages, **body only**. Full replay
    is the pinned context strategy: a consultation is a bounded amount of text,
    and a rolling summary is added only if token limits actually bite.
    """
    prompt = render_prompt(
        SYSTEM_PROMPT,
        is_opening=not history,
        preferences=[
            {
                "attribute": preference.attribute,
                # The customer's own words: stripped of anything resembling a
                # fence marker before it is rendered inside one (fencing.fence).
                "value": fence(preference.value),
                "firmness": preference.firmness.value,
            }
            for preference in preferences
        ],
        fence_start=FENCE_START,
        fence_end=FENCE_END,
    )
    messages: list[BaseMessage] = [SystemMessage(prompt)]
    for message in history:
        if message.role is ChatMessageRole.USER:
            messages.append(HumanMessage(message.body))
        else:
            messages.append(AIMessage(message.body))
    return messages


async def _loop(
    bound_model: Runnable[Any, Any],
    plain_model: BaseChatModel,
    messages: list[BaseMessage],
    ctx: tools.ToolContext,
    *,
    max_steps: int,
) -> AIMessage:
    """Run the tool loop and return the answer message.

    One iteration is one round: ask, and if the model asked for tools, run them
    all and ask again. `max_steps` rounds may request tools; when the budget is
    spent the model is asked once more **with the tools unbound**, so it cannot
    reach for another one and the turn ends with prose.
    """
    for step in range(max_steps):
        answer = await bound_model.ainvoke(messages)
        messages.append(answer)
        if not answer.tool_calls:
            return answer
        logger.info(
            "Agent step %d/%d: %s.",
            step + 1,
            max_steps,
            ", ".join(call["name"] for call in answer.tool_calls),
        )
        for call in answer.tool_calls:
            messages.append(await _run_call(ctx, call))

    logger.info("Agent tool budget of %d step(s) is spent; wrapping the turn up.", max_steps)
    messages.append(SystemMessage(WRAP_UP_INSTRUCTION))
    return await plain_model.ainvoke(messages)


async def _run_call(ctx: tools.ToolContext, call: dict[str, Any]) -> ToolMessage:
    """Execute one requested tool call and return the `ToolMessage` for it.

    Every outcome is a message, never an exception: a tool that failed, a tool
    that does not exist and arguments the schema rejected are all things the model
    can react to — reporting them is what lets it correct itself, and the failed
    ones are already in the collector (except the two that never executed).
    """
    name = call.get("name") or ""
    arguments = call.get("args") or {}
    call_id = call.get("id") or ""

    try:
        spec = tools.get_tool_spec(name)
    except KeyError:
        logger.warning("The model asked for the unregistered tool %r.", name)
        return _error_message(call_id, f"There is no tool named {name!r}.")

    try:
        payload = await tools.execute(spec, ctx, arguments)
    except Exception as error:
        # `execute` has already recorded the failure (and does not record a
        # validation error, because nothing ran) — this is the model's copy.
        return _error_message(call_id, f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS])

    return ToolMessage(content=json.dumps(payload, ensure_ascii=False), tool_call_id=call_id)


def _error_message(call_id: str, error: str) -> ToolMessage:
    """Return the failure of one tool call as the model reads it."""
    return ToolMessage(
        content=json.dumps({"error": error}, ensure_ascii=False),
        tool_call_id=call_id,
        status="error",
    )
