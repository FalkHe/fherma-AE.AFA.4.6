"""Shared model-build and usage-accounting helper for the decisions/
narration flow (sprint 011-06).

`build_model()` is the *only* place this flow constructs a `BaseChatModel`
- it goes through `llm_service.chat_model()`, never a vendor client
directly, so provider config and `LlmConfigurationError` stay owned by
`core/llm`.

`to_usage()` adapts `llm_service.usage_of()` (which reads one message) into
the flow's own `flow_state.Usage` checkpoint type, summed over every
`AIMessage` in a sequence - a decision or beat may call the model more than
once (tool loop), and the caller wants one total, not one per call.

`ainvoke()` is the only way this flow awaits a runnable: it always routes
through `llm_service.ainvoke_chat()` for retry + error translation, and
always passes `core/tracing`'s `langchain_config()` so the run shows up in
Langfuse under `label` as its name - never a bare `runnable.ainvoke()`.
"""

from collections.abc import Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable

from app.core.llm import service as llm_service
from app.core.tracing import service as tracing
from app.modules.game.agent.flow_state import Usage


def build_model() -> BaseChatModel:
    """Build the chat model for this flow, through the `core/llm` seam."""
    return llm_service.chat_model()


def to_usage(messages: Sequence[BaseMessage]) -> Usage:
    """Sum token counts and cost over every `AIMessage` in `messages`.

    Non-`AIMessage` entries (e.g. the `ToolMessage`s of a tool loop) carry
    no usage and are skipped. Cost sums the calls that report one; when
    none do, the total is `None` rather than `0` - a decision made of
    calls this provider never priced is not free, it is unknown.
    """
    prompt_tokens = 0
    completion_tokens = 0
    cost: float | None = None
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        call_usage = llm_service.usage_of(message)
        prompt_tokens += call_usage.prompt_tokens
        completion_tokens += call_usage.completion_tokens
        if call_usage.cost_usd is not None:
            cost = call_usage.cost_usd if cost is None else cost + call_usage.cost_usd

    return Usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
    )


async def ainvoke(runnable: Runnable, messages: object, *, label: str) -> AIMessage:
    """Await `runnable.ainvoke(messages)` through the traced, retried seam.

    `llm_service.ainvoke_chat()` passes no `config=` of its own (it exists
    for the already-traced game-turn graph) - this flow has no outer span,
    so `label` is bound onto the runnable itself via
    `tracing.langchain_config()` before handing it to `ainvoke_chat()` for
    retry + `LlmError` translation. `label` becomes the Langfuse run name.
    """
    bound = runnable.with_config(tracing.langchain_config(label))
    return await llm_service.ainvoke_chat(bound, messages, label=label)
