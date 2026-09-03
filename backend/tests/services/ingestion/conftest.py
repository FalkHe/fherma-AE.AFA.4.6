"""Fixtures for the ingestion layer tests.

Nothing here opens a socket: every fetch test drives a `MockTransport`, the
extraction tests read HTML from `fixtures/`, and the source adapters are driven
by recorded API responses from the same directory. The network is never a
dependency of this suite — that is what `app ingest fetch-url` and
`app ingest probe` are for.

The same holds for OpenRouter: an ingestion run reaches the specification
extraction stage (step 2.17) and the embedding stage (step 2.19), so the autouse
`extracted_specs` and `fake_embeddings` fixtures replace those two LLM calls for
**every** test in this package — the extraction, chunking and embedding services
themselves still run. A test that wants a failing extraction or a failing
embeddings gateway re-patches `app.llm.extraction.extract_spec` /
`app.llm.embeddings.get_embeddings` itself.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from app.core.config import get_settings
from app.llm import embeddings as llm_embeddings
from app.llm import extraction

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def extracted_specs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Answer the extraction stage's LLM call with a fixed specification.

    Returns the model names the stubbed extraction was asked about, so a test
    can prove the stage ran at all.
    """
    asked: list[str] = []

    async def extract_spec(
        name: str, documents: Any, *, model: str | None = None
    ) -> extraction.ExtractedSpec:
        asked.append(name)
        return extraction.ExtractedSpec.model_validate({"engine_cc": "599 cc", "power_kw": "72 kW"})

    monkeypatch.setattr(extraction, "extract_spec", extract_spec)
    return asked


class FakeEmbeddings:
    """Answers the embedding stage with correctly sized zero vectors."""

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    @property
    def texts(self) -> list[str]:
        """Every text this client was asked to embed, in order."""
        return [text for batch in self.batches for text in batch]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        return [[0.0] * get_settings().embedding_dimensions for _ in texts]


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> FakeEmbeddings:
    """Answer the embedding stage's gateway calls without a key or a socket."""
    client = FakeEmbeddings()
    monkeypatch.setattr(llm_embeddings, "get_embeddings", lambda model=None: client)
    return client


@pytest.fixture
def html_fixture() -> Callable[[str], str]:
    """Return a loader for the saved HTML pages in `fixtures/`."""

    def load(name: str) -> str:
        return (FIXTURES / name).read_text(encoding="utf-8")

    return load


@pytest.fixture
def json_fixture() -> Callable[[str], Any]:
    """Return a loader for the recorded API responses in `fixtures/`."""

    def load(name: str) -> Any:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))

    return load


@pytest.fixture
def settings_override(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Return a setter for settings the ingestion layer reads at call time."""

    def override(**environment: object) -> None:
        for key, value in environment.items():
            monkeypatch.setenv(key, str(value))
        get_settings.cache_clear()

    yield override
    get_settings.cache_clear()
