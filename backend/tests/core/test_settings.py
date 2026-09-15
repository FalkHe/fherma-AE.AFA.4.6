"""Intent 001 sprint 01 WI1: `Settings` carries the OpenRouter API key and
chat model that the LangChain seam (WI2) will read.

Intent 001 sprint 03 WI1: `Settings` also carries the retry attempt budget
and backoff base that the quiet-retry loop (WI3) will read.
"""

import importlib

import pytest
from pydantic import ValidationError

from app.core import settings as settings_module


def test_settings_exposes_openrouter_api_key_and_chat_model_with_documented_defaults(
    monkeypatch,
):
    # conftest.py pins OPENROUTER_API_KEY/CHAT_MODEL for the rest of the
    # suite; unset them here so the field defaults themselves are asserted.
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CHAT_MODEL", raising=False)

    instance = settings_module.Settings(
        _env_file=None, database_url="postgresql+psycopg://app:app@postgres:5432/x"
    )

    assert instance.openrouter_api_key == ""
    assert instance.chat_model == "openai/gpt-4.1-mini"


def test_importing_langchain_openrouter_is_warning_clean():
    importlib.import_module("langchain_openrouter")


def test_settings_exposes_llm_retry_attempts_and_backoff_with_documented_defaults(
    monkeypatch,
):
    monkeypatch.delenv("LLM_RETRY_ATTEMPTS", raising=False)
    monkeypatch.delenv("LLM_RETRY_BACKOFF_SECONDS", raising=False)

    instance = settings_module.Settings(
        _env_file=None, database_url="postgresql+psycopg://app:app@postgres:5432/x"
    )

    assert instance.llm_retry_attempts == 3
    assert instance.llm_retry_backoff_seconds == 0.5


def test_llm_retry_attempts_rejects_zero():
    with pytest.raises(ValidationError):
        settings_module.Settings(
            _env_file=None,
            database_url="postgresql+psycopg://app:app@postgres:5432/x",
            llm_retry_attempts=0,
        )


def test_llm_retry_backoff_seconds_rejects_negative():
    with pytest.raises(ValidationError):
        settings_module.Settings(
            _env_file=None,
            database_url="postgresql+psycopg://app:app@postgres:5432/x",
            llm_retry_backoff_seconds=-0.1,
        )
