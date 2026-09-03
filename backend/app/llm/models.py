"""The canonical chat-model factory: LangChain over OpenRouter, nothing else.

`get_chat_model()` is the single place where a chat model is built. OpenRouter
is the only gateway (never the OpenAI API directly), the default model comes
from configuration, and observability callbacks are attached centrally — so a
caller only ever decides *which* model, never *how* to reach it.
"""

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_openrouter import ChatOpenRouter
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler as LangfuseCallbackHandler

from app.core.config import Settings, get_settings

# OpenRouter attribution (sent as HTTP-Referer / X-Title by the integration).
# Deliberately constants and not configuration: they identify this application
# in the OpenRouter dashboard and are the same in every environment.
APP_TITLE = "Motorcycle Buying Advisor"
APP_URL = "https://github.com/TuringCollegeSubmissions/fherma-AE.AFA.3.5"

# Client-side timeout and retry policy (shared-knowledge D3). Module constants,
# not settings — the policy is fixed, not environment-specific. A stalled
# gateway call must fail (and retry through the job's own transient-error
# handling) well inside `AGENT_TIMEOUT_SECONDS`, not hang on the SDK default.
CHAT_REQUEST_TIMEOUT_SECONDS = 60
LLM_MAX_RETRIES = 2


class MissingApiKeyError(RuntimeError):
    """Raised when a model is requested without `OPENROUTER_API_KEY` configured.

    A dedicated type so callers (CLI commands, jobs) can report a configuration
    problem as such instead of surfacing a validation traceback.
    """

    def __init__(self) -> None:
        super().__init__("OPENROUTER_API_KEY is not configured.")


def observability_callbacks(settings: Settings) -> list[BaseCallbackHandler]:
    """Return the LangChain callback handlers every chat model is built with.

    Langfuse tracing, gated on all three `LANGFUSE_*` settings being non-empty
    (otherwise `[]`, byte-identical to no observability at all — a Langfuse
    outage or missing configuration must never fail an LLM call). Embeddings
    are deliberately excluded: LangChain embeddings emit no callback events, a
    documented limitation, not an oversight.

    `langfuse~=4.0`'s `CallbackHandler` (`langfuse.langchain`) only takes
    `public_key`/`trace_context` — `secret_key` and `host` are not constructor
    arguments there. They are passed to the `Langfuse` client instead, which
    registers itself as the active client the handler then reports through.
    """
    configured = (
        settings.langfuse_public_key,
        settings.langfuse_secret_key,
        settings.langfuse_host,
    )
    if not all(configured):
        return []

    Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return [LangfuseCallbackHandler()]


def get_chat_model(model: str | None = None) -> ChatOpenRouter:
    """Return a chat model talking to OpenRouter.

    `model` overrides the configured default (`CHAT_MODEL`) and takes an
    OpenRouter model identifier such as `openai/gpt-4.1-mini`.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise MissingApiKeyError

    return ChatOpenRouter(
        model=model or settings.chat_model,
        api_key=settings.openrouter_api_key,
        app_url=APP_URL,
        app_title=APP_TITLE,
        callbacks=observability_callbacks(settings) or None,
        # `ChatOpenRouter.timeout` is documented in *milliseconds* (maps to the
        # SDK's `timeout_ms`) — shared-knowledge D3 amendment, verified against
        # the installed `langchain_openrouter` — hence the conversion.
        timeout=CHAT_REQUEST_TIMEOUT_SECONDS * 1000,
        max_retries=LLM_MAX_RETRIES,
    )
