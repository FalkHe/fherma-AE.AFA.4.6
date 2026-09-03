"""Tests for the embeddings factory.

Nothing is embedded here: these tests assert how the client is *wired* — the
gateway it talks to, the model id, and the one flag that decides whether the
requests are even acceptable to an OpenAI-compatible gateway. All of it is
observable on the constructed object.
"""

from collections.abc import Iterator

import pytest

from app.core.config import get_settings
from app.llm.embeddings import (
    EMBEDDINGS_REQUEST_TIMEOUT_SECONDS,
    OPENROUTER_API_BASE,
    get_embeddings,
)
from app.llm.models import LLM_MAX_RETRIES, MissingApiKeyError

# Syntactically usable and deliberately never dialled, like the URLs pinned in
# the top-level conftest.
TEST_API_KEY = "test-openrouter-key"

CONFIGURED_MODEL = "openai/text-embedding-3-large"


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide a key and a non-default embedding model through the environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", TEST_API_KEY)
    monkeypatch.setenv("EMBEDDING_MODEL", CONFIGURED_MODEL)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def without_api_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Provide the empty-key configuration that ships in `.env.dist`."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("configured")
def test_default_model_comes_from_settings() -> None:
    """Without an argument the factory uses `EMBEDDING_MODEL`."""
    assert get_embeddings().model == CONFIGURED_MODEL


@pytest.mark.usefixtures("configured")
def test_model_argument_overrides_the_default() -> None:
    """An explicit model id wins over the configured default."""
    assert get_embeddings("openai/text-embedding-3-small").model == "openai/text-embedding-3-small"


@pytest.mark.usefixtures("configured")
def test_requests_go_to_openrouter_with_the_configured_key() -> None:
    """OpenRouter is the gateway — the OpenAI API is never addressed directly."""
    client = get_embeddings()

    assert client.openai_api_base == OPENROUTER_API_BASE == "https://openrouter.ai/api/v1"
    assert client.openai_api_key is not None
    assert client.openai_api_key.get_secret_value() == TEST_API_KEY


@pytest.mark.usefixtures("configured")
def test_context_length_check_is_disabled() -> None:
    """Mandatory: with the check on, LangChain sends token arrays a gateway rejects.

    See LangChain issue #35204 — this is the whole reason the flag is pinned.
    """
    assert get_embeddings().check_embedding_ctx_length is False


@pytest.mark.usefixtures("configured")
def test_no_dimensions_parameter_is_sent() -> None:
    """The model's native vector size already matches the column."""
    assert get_embeddings().dimensions is None


@pytest.mark.usefixtures("configured")
def test_timeout_and_retries_are_wired() -> None:
    """The client-side policy (shared-knowledge D3) reaches the constructed client.

    Unlike `ChatOpenRouter`, `OpenAIEmbeddings.timeout` is seconds (the OpenAI
    SDK's own convention) — the constant is passed straight through.
    """
    client = get_embeddings()

    assert client.request_timeout == EMBEDDINGS_REQUEST_TIMEOUT_SECONDS
    assert client.max_retries == LLM_MAX_RETRIES


@pytest.mark.usefixtures("without_api_key")
def test_missing_api_key_raises_a_configuration_error() -> None:
    """An empty key is reported as configuration, not as a validation error."""
    with pytest.raises(MissingApiKeyError, match="OPENROUTER_API_KEY is not configured"):
        get_embeddings()
