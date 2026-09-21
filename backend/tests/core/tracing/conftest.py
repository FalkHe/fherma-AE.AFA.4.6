"""Fixtures for the tracing seam's tests.

The module under test keeps its Langfuse client in a module-level global
(`tracing._client`), which is exactly the kind of state that leaks between
tests: one test that configures tracing would otherwise leave every later
test in the process talking to a fake Langfuse. `_tracing_off_after_every_test`
is autouse and resets it unconditionally.

Nothing here ever constructs a real `Langfuse`: `FakeLangfuse` is
monkeypatched onto `tracing.Langfuse` by the tests that need the enabled
path, so no test opens a socket or needs credentials.
"""

from contextlib import contextmanager

import pytest

from app.core.tracing import service as tracing


@pytest.fixture(autouse=True)
def _tracing_off_after_every_test():
    yield
    tracing._client = None


class FakeObservation:
    """Stands in for a Langfuse observation. Records every `.update()`."""

    def __init__(self, name: str, as_type: str, attributes: dict):
        self.name = name
        self.as_type = as_type
        self.attributes = attributes
        self.updates: list[dict] = []
        self.closed = False

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


class FakeLangfuse:
    """Stands in for `langfuse.Langfuse`, monkeypatched onto
    `tracing.Langfuse`. `.kwargs` records the constructor call, so a test
    can assert the base URL, the environment and the masking hook actually
    reach the SDK."""

    instances: list["FakeLangfuse"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.observations: list[FakeObservation] = []
        self.flushed = 0
        self.was_shut_down = False
        type(self).instances.append(self)

    @contextmanager
    def start_as_current_observation(self, *, name, as_type, **attributes):
        observation = FakeObservation(name, as_type, attributes)
        self.observations.append(observation)
        try:
            yield observation
        finally:
            observation.closed = True

    def flush(self) -> None:
        self.flushed += 1

    def shutdown(self) -> None:
        self.was_shut_down = True


@pytest.fixture
def fake_langfuse(monkeypatch):
    """Returns the `FakeLangfuse` class with a per-test `.instances` list."""

    class _FakeLangfuse(FakeLangfuse):
        instances: list = []

    monkeypatch.setattr(tracing, "Langfuse", _FakeLangfuse)
    return _FakeLangfuse


@pytest.fixture
def enabled_tracing(monkeypatch, fake_langfuse):
    """Tracing configured against a `FakeLangfuse`. Yields the instance."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.example")
    _clear_settings_cache()
    try:
        tracing.configure()
        yield fake_langfuse.instances[-1]
    finally:
        tracing._client = None
        _clear_settings_cache()


def _clear_settings_cache() -> None:
    from app.core.settings import get_settings

    get_settings.cache_clear()
