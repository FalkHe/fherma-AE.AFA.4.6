"""Intent 001 sprint 01 WI1: `Settings` carries the OpenRouter API key and
chat model that the LangChain seam (WI2) will read.
"""

import importlib

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
