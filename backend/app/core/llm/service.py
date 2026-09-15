"""The seam between this app and OpenRouter chat models.

`chat_model()` hands back a configured `ChatOpenRouter` (a LangChain
`BaseChatModel`); `usage_of()` reads token counts and USD cost off a reply.
Callers use the module reference (`from app.core.llm import service as
llm_service`), never a name import - tests monkeypatch `service.ChatOpenRouter`
and `service.get_settings`.
"""

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openrouter import ChatOpenRouter

from app.core.llm.errors import LlmConfigurationError
from app.core.settings import get_settings

DEFAULT_TEMPERATURE = 0.7


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None


def chat_model(*, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
    """Return a configured OpenRouter chat model.

    `model`/`temperature` fall back to `get_settings().chat_model` and
    `DEFAULT_TEMPERATURE` respectively when omitted. Raises
    `LlmConfigurationError` when `OPENROUTER_API_KEY` is blank, before
    `ChatOpenRouter` is constructed at all - its own
    `validate_environment` would otherwise raise a bare `ValueError` at
    construction time.

    `stream_usage` is left at `ChatOpenRouter`'s own default (`True`), so a
    streaming caller's final chunk still carries `usage_metadata` for
    `usage_of()` to read.
    """
    settings = get_settings()
    if not settings.openrouter_api_key.strip():
        raise LlmConfigurationError()

    return ChatOpenRouter(
        model=model if model is not None else settings.chat_model,
        temperature=temperature if temperature is not None else DEFAULT_TEMPERATURE,
        api_key=settings.openrouter_api_key,
    )


def usage_of(message: BaseMessage) -> Usage:
    """Read token counts and USD cost off a chat reply.

    Counts come from `message.usage_metadata`
    (`input_tokens`/`output_tokens`/`total_tokens`); cost from
    `message.response_metadata["cost"]`. Either absent degrades to zeros /
    `None` rather than raising - not every message (or every provider reply)
    carries usage.
    """
    usage_metadata = getattr(message, "usage_metadata", None) or {}
    cost = message.response_metadata.get("cost")

    return Usage(
        prompt_tokens=usage_metadata.get("input_tokens", 0),
        completion_tokens=usage_metadata.get("output_tokens", 0),
        total_tokens=usage_metadata.get("total_tokens", 0),
        cost_usd=cost,
    )
