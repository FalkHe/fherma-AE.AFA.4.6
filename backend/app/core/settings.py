from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    database_url: str
    session_ttl_seconds: int = 1209600
    frontend_origin: str = "http://localhost:5173"
    openrouter_api_key: str = ""
    chat_model: str = "openai/gpt-4.1-mini"
    llm_retry_attempts: int = Field(default=3, ge=1)
    llm_retry_backoff_seconds: float = Field(default=0.5, ge=0)
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dimensions: int = Field(default=1536, ge=1)
    image_model: str = "google/gemini-3.1-flash-image"
    sse_poll_interval_seconds: float = Field(default=2.0, gt=0)
    sse_max_lifetime_seconds: float = Field(default=300.0, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
