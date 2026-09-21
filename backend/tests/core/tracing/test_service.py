"""The tracing seam (`app/core/tracing/service.py`).

Two properties matter more than any individual assertion here and most of
this file exists to pin them:

1. **Blank credentials mean off, not broken.** A fresh checkout has no
   Langfuse keys, and every function in the module has to be a no-op in
   that state - no client, no callbacks, no exceptions.
2. **Langfuse can never fail a model call.** Every entry point is asserted
   against a Langfuse that raises, and every one of them has to degrade
   quietly instead of propagating.

No test constructs a real `Langfuse`: `conftest.py`'s `FakeLangfuse` is
monkeypatched onto `tracing.Langfuse`, so the suite needs no credentials
and opens no socket.
"""

import importlib
from types import SimpleNamespace

import pytest

from app.core.settings import get_settings
from app.core.tracing import service as tracing


def test_importing_langfuse_is_warning_clean():
    # `filterwarnings = ["error"]` makes any warning at import time fatal
    # for the whole suite, so the import is pinned in a test of its own -
    # the same guard `test_settings.py` puts on langchain_openrouter.
    importlib.import_module("langfuse")
    importlib.import_module("langfuse.langchain")


# --------------------------------------------------------------------------
# configure()
# --------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"])
def test_configure_leaves_tracing_off_when_a_credential_is_blank(monkeypatch, fake_langfuse, blank):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.example")
    monkeypatch.setenv(blank, "   ")
    get_settings.cache_clear()

    try:
        tracing.configure()
        assert tracing.enabled() is False
        assert fake_langfuse.instances == []
    finally:
        get_settings.cache_clear()


def test_configure_leaves_tracing_off_when_no_credentials_are_set(fake_langfuse):
    # The suite-wide environment (tests/conftest.py) sets no LANGFUSE_*
    # variables at all: this is the default a fresh checkout runs in.
    tracing.configure()

    assert tracing.enabled() is False
    assert fake_langfuse.instances == []


def test_configure_passes_credentials_environment_and_masking_hook(enabled_tracing):
    assert tracing.enabled() is True
    assert enabled_tracing.kwargs["public_key"] == "pk-lf-test"
    assert enabled_tracing.kwargs["secret_key"] == "sk-lf-test"
    assert enabled_tracing.kwargs["base_url"] == "https://langfuse.example"
    # The deployment environment is a first-class Langfuse field, not
    # metadata: it is what keeps development traces out of production
    # dashboards and evaluators.
    assert enabled_tracing.kwargs["environment"] == "development"
    assert enabled_tracing.kwargs["mask_otel_spans"] is tracing.mask_otel_spans


def test_configure_is_idempotent(enabled_tracing, fake_langfuse):
    tracing.configure()

    assert len(fake_langfuse.instances) == 1


def test_configure_swallows_a_client_that_refuses_to_build(monkeypatch):
    def _explode(**kwargs):
        raise RuntimeError("bad base url")

    monkeypatch.setattr(tracing, "Langfuse", _explode)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://langfuse.example")
    get_settings.cache_clear()

    try:
        tracing.configure()
        assert tracing.enabled() is False
    finally:
        get_settings.cache_clear()


# --------------------------------------------------------------------------
# langchain_config()
# --------------------------------------------------------------------------


def test_langchain_config_carries_only_the_run_name_when_tracing_is_off():
    assert tracing.langchain_config("invoke-chat-model") == {"run_name": "invoke-chat-model"}


def test_langchain_config_carries_the_callback_handler_when_tracing_is_on(
    enabled_tracing, monkeypatch
):
    handlers = []

    class _FakeHandler:
        def __init__(self):
            handlers.append(self)

    monkeypatch.setattr(tracing, "CallbackHandler", _FakeHandler)

    config = tracing.langchain_config("invoke-chat-model", metadata={"feature": "chat"})

    assert config["run_name"] == "invoke-chat-model"
    assert config["metadata"] == {"feature": "chat"}
    assert config["callbacks"] == handlers


def test_langchain_config_still_returns_a_usable_config_when_the_handler_fails(
    enabled_tracing, monkeypatch
):
    def _explode():
        raise RuntimeError("no handler for you")

    monkeypatch.setattr(tracing, "CallbackHandler", _explode)

    config = tracing.langchain_config("invoke-chat-model")

    assert config == {"run_name": "invoke-chat-model"}


# --------------------------------------------------------------------------
# observe()
# --------------------------------------------------------------------------


def test_observe_yields_a_no_op_when_tracing_is_off():
    with tracing.observe("embed-texts") as observation:
        # The call site updates unconditionally; with tracing off that has
        # to be harmless rather than an AttributeError.
        observation.update(output={"vectorCount": 1})


def test_observe_opens_and_closes_a_typed_observation(enabled_tracing):
    with tracing.observe(
        "create-embeddings", as_type="embedding", model="test/embedding-model"
    ) as observation:
        observation.update(output={"vectorCount": 2})

    recorded = enabled_tracing.observations[0]
    assert recorded.name == "create-embeddings"
    assert recorded.as_type == "embedding"
    assert recorded.attributes["model"] == "test/embedding-model"
    assert recorded.updates == [{"output": {"vectorCount": 2}}]
    assert recorded.closed is True


def test_observe_defaults_to_a_span(enabled_tracing):
    with tracing.observe("generate-chat-reply"):
        pass

    assert enabled_tracing.observations[0].as_type == "span"


def test_observe_runs_the_block_when_langfuse_refuses_to_open_an_observation(
    enabled_tracing, monkeypatch
):
    def _explode(**kwargs):
        raise RuntimeError("langfuse is down")

    monkeypatch.setattr(enabled_tracing, "start_as_current_observation", _explode)
    ran = False

    with tracing.observe("generate-chat-reply") as observation:
        observation.update(output="still fine")
        ran = True

    assert ran is True


# --------------------------------------------------------------------------
# trace_context()
# --------------------------------------------------------------------------


def test_trace_context_is_a_no_op_when_tracing_is_off():
    with tracing.trace_context(user_id="u1", session_id="s1"):
        pass


def test_trace_context_propagates_attributes_when_tracing_is_on(enabled_tracing, monkeypatch):
    recorded = {}

    class _FakePropagation:
        def __enter__(self):
            return None

        def __exit__(self, *exc):
            return False

    def _propagate(**attributes):
        recorded.update(attributes)
        return _FakePropagation()

    monkeypatch.setattr(tracing, "propagate_attributes", _propagate)

    with tracing.trace_context(user_id="u1", session_id="s1"):
        pass

    assert recorded == {"user_id": "u1", "session_id": "s1"}


def test_trace_context_runs_the_block_when_propagation_fails(enabled_tracing, monkeypatch):
    def _explode(**attributes):
        raise RuntimeError("langfuse is down")

    monkeypatch.setattr(tracing, "propagate_attributes", _explode)
    ran = False

    with tracing.trace_context(user_id="u1"):
        ran = True

    assert ran is True


# --------------------------------------------------------------------------
# flush() / shutdown()
# --------------------------------------------------------------------------


def test_flush_and_shutdown_are_no_ops_when_tracing_is_off():
    tracing.flush()
    tracing.shutdown()


def test_flush_sends_what_is_buffered(enabled_tracing):
    tracing.flush()

    assert enabled_tracing.flushed == 1


def test_shutdown_stops_the_client_and_turns_tracing_off(enabled_tracing):
    tracing.shutdown()

    assert enabled_tracing.was_shut_down is True
    assert tracing.enabled() is False


def test_shutdown_turns_tracing_off_even_when_the_client_raises(enabled_tracing, monkeypatch):
    def _explode():
        raise RuntimeError("langfuse is down")

    monkeypatch.setattr(enabled_tracing, "shutdown", _explode)

    tracing.shutdown()

    assert tracing.enabled() is False


# --------------------------------------------------------------------------
# mask_otel_spans()
# --------------------------------------------------------------------------


def _params(**attributes):
    """A stand-in for `MaskOtelSpansParams`: the hook reads nothing but
    `params.spans[...].attributes`."""
    return SimpleNamespace(spans={"span-1": SimpleNamespace(attributes=attributes)})


@pytest.mark.parametrize(
    "secret",
    [
        "sk-or-v1-0123456789abcdef0123456789abcdef",
        "sk-lf-2c1581dd-9cec-dafb-6ca0-91b83d7ea99a",
        "pk-lf-2c1581dd-9cec-dafb-6ca0-91b83d7ea99a",
        "sk-proj-AAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        "Bearer eyJhbGciOiJIUzI1NiwidHlwIjoiSldUIn0",
    ],
)
def test_masking_redacts_credentials(secret):
    result = tracing.mask_otel_spans(params=_params(**{"langfuse.observation.input": secret}))

    masked = result.span_patches["span-1"].set_attributes["langfuse.observation.input"]
    assert secret not in masked
    assert tracing.REDACTED in masked


def test_masking_redacts_email_addresses_without_touching_the_rest():
    result = tracing.mask_otel_spans(
        params=_params(**{"langfuse.observation.input": "write to falk@example.com about the orc"})
    )

    masked = result.span_patches["span-1"].set_attributes["langfuse.observation.input"]
    assert masked == f"write to {tracing.REDACTED} about the orc"


def test_masking_patches_nothing_when_a_span_is_clean():
    result = tracing.mask_otel_spans(
        params=_params(**{"langfuse.observation.input": "The goblin attacks.", "count": 3})
    )

    assert result.span_patches == {}
