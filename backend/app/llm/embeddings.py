"""The canonical embeddings factory: LangChain over OpenRouter, nothing else.

`get_embeddings()` is the embeddings counterpart of `models.get_chat_model()`.
OpenRouter stays the only gateway (never the OpenAI API directly), but
`langchain-openrouter` ships no embeddings class — so the OpenAI-compatible
LangChain wrapper is pointed at OpenRouter's own OpenAI-shaped
`POST /api/v1/embeddings` route. The package is a *protocol* client here, not a
provider: no request ever leaves for `api.openai.com`.

Two details are load-bearing and must not be "cleaned up":

* **`check_embedding_ctx_length=False` is mandatory.** With the default,
  LangChain pre-tokenizes every input and sends token *arrays* instead of
  strings, which OpenAI-compatible gateways reject (LangChain issue #35204).
* **No `dimensions` parameter is sent.** The pinned model's native vector size
  already matches the `chunks.embedding` column, and OpenRouter's pass-through
  of that parameter is undocumented.
"""

import openrouter
from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings
from app.llm.models import LLM_MAX_RETRIES, MissingApiKeyError

# OpenRouter's own API base, taken from the SDK that ships with
# langchain-openrouter instead of being spelled out here.
OPENROUTER_API_BASE = openrouter.SERVERS[openrouter.SERVER_PRODUCTION]

# Client-side timeout (shared-knowledge D3). A module constant, not a setting —
# this closes the step-3.9 finding of a stalled embeddings call hanging on the
# SDK's ~600 s default. `OpenAIEmbeddings.timeout` is seconds (the OpenAI SDK's
# own convention), unlike `ChatOpenRouter.timeout` (milliseconds) — no
# conversion here. `LLM_MAX_RETRIES` is reused from `app.llm.models` so the
# retry policy is one number, not one per client.
EMBEDDINGS_REQUEST_TIMEOUT_SECONDS = 30


def get_embeddings(model: str | None = None) -> OpenAIEmbeddings:
    """Return an embeddings client talking to OpenRouter.

    `model` overrides the configured default (`EMBEDDING_MODEL`) and takes an
    OpenRouter model identifier such as `openai/text-embedding-3-small`.

    Raises:
        MissingApiKeyError: `OPENROUTER_API_KEY` is not configured. Callers
            treat this as a configuration problem, never as a transient one —
            a retry cannot set a key.
    """
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise MissingApiKeyError

    return OpenAIEmbeddings(
        model=model or settings.embedding_model,
        base_url=OPENROUTER_API_BASE,
        api_key=settings.openrouter_api_key,
        check_embedding_ctx_length=False,
        timeout=EMBEDDINGS_REQUEST_TIMEOUT_SECONDS,
        max_retries=LLM_MAX_RETRIES,
    )
