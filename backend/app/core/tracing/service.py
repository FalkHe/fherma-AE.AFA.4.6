"""The seam between this app and Langfuse.

Tracing is *optional and never load-bearing*. `configure()` builds the
Langfuse client once, from `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` /
`LANGFUSE_BASE_URL`; with any of the three blank the whole module degrades
to no-ops and the application behaves byte-identically. Every Langfuse
call in here is wrapped so that a Langfuse outage, a wrong key or a
network stall can never turn into a failed model call - the worst case is
a `tracing_failed` warning on stderr and a missing trace.

Callers use the module reference (`from app.core import tracing`), never a
name import - tests monkeypatch `tracing._client` and
`tracing.CallbackHandler`.

What the rest of the app uses:

- `langchain_config(name, ...)` - the `config=` dict handed to a LangChain
  `.invoke()` / `.stream()`. It carries the Langfuse `CallbackHandler`,
  which is what captures model name, token usage and cost on a
  `generation` observation without this app computing any of it (← the
  framework integration is always preferred over manual instrumentation).
  With tracing off it still carries `run_name`, which LangChain accepts
  either way, so the call site has no branch in it.
- `observe(name, as_type=...)` - a context manager for the calls LangChain
  cannot see: the OpenRouter SDK's own embeddings and images endpoints
  (`core/llm/service.py`). Yields something with `.update(...)` whether or
  not tracing is on.
- `trace_context(...)` - trace-level attributes (`user_id`, `session_id`,
  `tags`) for request-scoped work. Nothing calls the model inside a
  request yet; the game module will, and this is the documented way to
  group a campaign run's turns into one Langfuse session.
- `flush()` / `shutdown()` - Langfuse batches in a background thread, so a
  Typer one-off has to flush before the process exits or the trace is lost
  (`app/cli.py`), and the API flushes on lifespan shutdown (`app/main.py`).

Trace shape (← https://langfuse.com/docs/observability/best-practices):
one trace per self-contained unit of work, named verb-first and with no
dynamic values in the name. Each LLM entry point opens one root span
(`generate-chat-reply`, `embed-texts`, `generate-image`) *outside* the
retry loop, so every retried attempt shows up as its own child
observation underneath it rather than as a separate trace - the attempt
count is then readable straight off the tree.

Masking: `mask_otel_spans()` runs at export time over raw OpenTelemetry
span attributes, including any a third-party instrumentation produced, and
redacts API keys and e-mail addresses before anything leaves the process.
It is the last line of defence, not the first: prompts sent to Langfuse
are the same prompts sent to OpenRouter.
"""

import atexit
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog
from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler
from langfuse.media import LangfuseMedia
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch

from app.core.settings import get_settings

logger = structlog.get_logger()

__all__ = [
    "LangfuseMedia",
    "configure",
    "enabled",
    "flush",
    "langchain_config",
    "mask_otel_spans",
    "observe",
    "shutdown",
    "trace_context",
]

# Built by `configure()`, read by everything else. `None` means tracing is
# off - either it was never configured or the credentials are incomplete.
_client: Langfuse | None = None

REDACTED = "[REDACTED]"

# One pattern for every API-key shape in play - OpenRouter's `sk-or-v1-…`,
# Langfuse's `pk-lf-…` / `sk-lf-…`, OpenAI's `sk-proj-…` - plus a generic
# bearer token. Deliberately narrow: this runs on the export worker thread
# for every attribute of every exported span, so it must stay cheap, and an
# over-broad pattern would redact ordinary prompt text.
_SECRET_PATTERNS = (
    re.compile(r"\b[ps]k-[A-Za-z0-9._-]{16,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}"),
)
_EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def _redact(value: str) -> str:
    masked = _EMAIL_PATTERN.sub(REDACTED, value)
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub(REDACTED, masked)
    return masked


def mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    """Redact credentials and e-mail addresses out of exported spans.

    Returns sparse patches: only the attributes that actually changed are
    sent back, and a span with nothing to redact produces no patch at all.
    Runs on the OpenTelemetry batch-processor worker thread (and, during
    `flush()`, on the caller's), so it stays regex-only - no I/O, no
    parsing of the payload.
    """
    patches: dict[Any, OtelSpanPatch] = {}

    for identifier, span in params.spans.items():
        replacements = {}
        for key, value in span.attributes.items():
            if isinstance(value, str) and (masked := _redact(value)) != value:
                replacements[key] = masked
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)

    return MaskOtelSpansResult(span_patches=patches)


def configure() -> None:
    """Build the Langfuse client, or leave tracing off.

    Idempotent: called from both `create_app()` and the Typer callback, and
    a second call with a client already built is a no-op. Blank credentials
    are the documented "tracing off" state, not an error - they get one
    DEBUG line, never a warning, because running without Langfuse is a
    supported mode (a fresh checkout has no keys).

    A client that cannot be constructed at all (bad URL, SDK refusing the
    configuration) is logged and swallowed: failing to start the API
    because an *optional* observability backend is unhappy would be the
    wrong trade.
    """
    global _client

    if _client is not None:
        return

    settings = get_settings()
    public_key = settings.langfuse_public_key.strip()
    secret_key = settings.langfuse_secret_key.strip()
    base_url = settings.langfuse_base_url.strip()

    if not (public_key and secret_key and base_url):
        logger.debug("tracing_disabled")
        return

    try:
        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            # A first-class Langfuse environment, not metadata: it keeps
            # development traces out of production dashboards and evals.
            environment=settings.environment,
            mask_otel_spans=mask_otel_spans,
        )
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="configure", error=str(exc))
        return

    # Short-lived processes (every Typer command) would otherwise exit
    # with the trace still buffered on the ingestion thread. The SDK
    # registers a hook of its own; this one is `shutdown()` as this module
    # defines it - idempotent, and it clears `_client` so a later
    # `configure()` in the same process starts clean.
    atexit.register(shutdown)

    logger.info("tracing_enabled", base_url=base_url, environment=settings.environment)


def enabled() -> bool:
    return _client is not None


def langchain_config(name: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """The `config=` dict for a LangChain `.invoke()` / `.stream()`.

    `run_name` names the observation LangChain reports (verb-first, no
    dynamic values). The `CallbackHandler` is what turns that report into a
    Langfuse `generation` carrying model, token usage and cost, nested
    under whatever `observe()` span is active. With tracing off only
    `run_name` is returned, which LangChain ignores harmlessly - the call
    site stays branch-free.
    """
    config: dict[str, Any] = {"run_name": name}
    if metadata:
        config["metadata"] = metadata
    if _client is None:
        return config

    try:
        config["callbacks"] = [CallbackHandler()]
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="callback_handler", error=str(exc))

    return config


class _NullObservation:
    """Stand-in yielded by `observe()` when tracing is off, so call sites
    can `.update(...)` unconditionally."""

    def update(self, **kwargs: Any) -> None:
        return None


@contextmanager
def observe(name: str, *, as_type: str = "span", **attributes: Any) -> Iterator[Any]:
    """Open one Langfuse observation for the duration of the block.

    `as_type` picks the observation type - `span` for a plain step,
    `generation` for a model call, `embedding` for an embedding call. The
    type is what makes Langfuse treat the observation as a model call at
    all (model, tokens, cost) and what evaluators and dashboards filter on,
    so the most specific type always wins over a generic span.

    Yields an object with `.update(...)`: the real Langfuse observation
    when tracing is on, a `_NullObservation` otherwise. A failure anywhere
    in the Langfuse machinery degrades to the null object mid-block rather
    than propagating - the wrapped work must not care whether it is being
    traced.
    """
    if _client is None:
        yield _NullObservation()
        return

    try:
        manager = _client.start_as_current_observation(name=name, as_type=as_type, **attributes)
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="observe", name=name, error=str(exc))
        yield _NullObservation()
        return

    with manager as observation:
        yield observation


@contextmanager
def trace_context(**attributes: Any) -> Iterator[None]:
    """Attach trace-level attributes (`user_id`, `session_id`, `tags`, ...)
    to every observation opened inside the block.

    The Langfuse-documented way to group traces: one trace per turn,
    `session_id` tying a conversation's turns together in the session
    replay view, `user_id` attributing cost and quality per player.
    """
    if _client is None:
        yield
        return

    try:
        manager = propagate_attributes(**attributes)
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="trace_context", error=str(exc))
        yield
        return

    with manager:
        yield


def flush() -> None:
    """Send everything buffered so far, blocking until it is gone.

    Langfuse ingests in a background thread, so a short-lived process
    (every Typer command) loses its trace without this.
    """
    if _client is None:
        return

    try:
        _client.flush()
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="flush", error=str(exc))


def shutdown() -> None:
    """Flush and stop the background threads. Called on API lifespan
    shutdown; the SDK also registers its own `atexit` hook, which this does
    not replace."""
    global _client

    if _client is None:
        return

    try:
        _client.shutdown()
    except Exception as exc:  # pragma: no cover - defensive, SDK-dependent
        logger.warning("tracing_failed", stage="shutdown", error=str(exc))
    finally:
        _client = None
