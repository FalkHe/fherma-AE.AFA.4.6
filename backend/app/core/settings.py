from functools import lru_cache
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
