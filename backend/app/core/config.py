"""Typed application settings, loaded from environment variables and `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# .../backend/app/core/config.py -> repository root
_REPO_ROOT = Path(__file__).resolve().parents[3]

Environment = Literal["development", "production"]
LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]

# Web search backends behind `app.services.ingestion.search.SearchProvider`.
# `openrouter` reuses `OPENROUTER_API_KEY` / `CHAT_MODEL` (its web plugin);
# `tavily` needs `TAVILY_API_KEY`.
SearchProviderName = Literal["tavily", "openrouter"]


class Settings(BaseSettings):
    """Application configuration.

    Values come from the process environment (how the Docker containers are
    configured) and fall back to a `.env` file for local, non-container runs.
    A missing required value fails fast at startup instead of being guessed.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", _REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    redis_url: str
    environment: Environment = "development"
    log_level: LogLevel = "INFO"

    # Ingestion: where retained payloads live and how much of a remote page we
    # are willing to spend time and memory on.
    data_dir: Path = Path("/app/var/data")
    ingestion_fetch_timeout_seconds: float = 20
    ingestion_max_fetch_bytes: int = 5_242_880

    # Images: where the downloaded originals and their generated variants live.
    # Served read-only by the `/media` static mount.
    media_dir: Path = Path("/app/var/media")

    # Ingestion: the web-search half. An empty key is a valid configuration —
    # ingestion then runs Wikipedia-only with a warning.
    search_provider: SearchProviderName = "tavily"
    tavily_api_key: str = ""
    ingestion_max_web_documents: int = 6

    # LLM access: OpenRouter is the only gateway. An empty key is a valid
    # configuration (the app starts, model calls report the missing key).
    openrouter_api_key: str = ""
    chat_model: str = "openai/gpt-4.1-mini"

    # The advisor's own model: the customer-facing responder and, from step
    # 3.13, its agent loop. Split from `chat_model` (ingestion, extraction and
    # utility calls) so the conversation can be moved to a stronger model
    # without changing what the catalogue pipeline costs.
    advisor_model: str = "openai/gpt-4.1-mini"

    # Embeddings: the model the knowledge base is vectorised with and the width
    # of the vectors it returns. `embedding_dimensions` must match the `vector`
    # column of `chunks` — a mismatch is a loud failure, never a truncation.
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Specification extraction: the character-based input budget (no tokenizer
    # dependency) one extraction call may spend on source documents.
    extraction_max_input_chars: int = 60_000

    # Chunking: the structural splitter's target slice size and the overlap
    # carried between two neighbouring slices, both in characters.
    chunk_size_chars: int = 3_200
    chunk_overlap_chars: int = 400

    # Hybrid retrieval: the Reciprocal Rank Fusion constant (larger flattens the
    # advantage of the top ranks) and how many candidates each of the two legs
    # contributes before fusion.
    rrf_k: int = 60
    retrieval_candidates_per_leg: int = 50

    # The advisor's agent loop: how many tool rounds one turn may spend before it
    # has to answer with what it has, and how long the whole turn may take. The
    # timeout is also the basis of the stale-turn threshold
    # (`chat_service.stale_turn_seconds()`), so the API starts accepting messages
    # again shortly after a turn can no longer be alive.
    agent_max_tool_steps: int = 8
    agent_timeout_seconds: float = 120

    # Used-price staleness: how many days old a `motorbike_used_prices`
    # snapshot may be before `used_price_service` reports it as stale. Staleness
    # is a caveat, never a refusal (D10) — the estimator still uses the price
    # and names the date.
    used_price_max_age_days: int = 180

    # Observability: Langfuse tracing of chat-model calls, entirely optional.
    # Empty (the default) means `observability_callbacks` attaches nothing and
    # the app behaves byte-identically; all three must be set to enable it.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (usable with `Depends`)."""
    return Settings()
