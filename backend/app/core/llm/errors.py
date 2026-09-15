"""Every LLM-access failure the seam can raise.

`LlmError` is the plug-in point FastAPI's `register_error_handlers`
(`app/core/errors.py`) catches; the player always sees the one generic line
(`LLM_FAILURE_MESSAGE`) regardless of which subclass fired (← D2). The eight
subclasses below carry the provider-facing detail (`.code`, `.retryable`,
`.provider_message`) for logging and for sprint 03's retry logic, never for
display.

`classify(exc)` is the seam's only entry point for turning a caught
exception into one of these: it dispatches purely on `.status_code` for
OpenRouter SDK errors (never on the class, since the SDK has many undocumented
subclasses and degrades to `OpenRouterDefaultError` on a non-JSON body), plus
a handful of client-side exception types. `raise_for_finish_reason` exists
because a mid-stream failure or a content-filter refusal from OpenRouter
arrives as a normal, successful chunk (exit 0) with the failure only visible
in `response_metadata["finish_reason"]` - there is no exception to classify.
"""

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage
from pydantic_core import ValidationError as PydanticValidationError

from app.core.errors import LLM_FAILURE_MESSAGE, ErrorCode
from app.core.settings import get_settings

try:
    from httpx import ConnectError as HttpxConnectError
    from httpx import TimeoutException as HttpxTimeoutException
except ImportError:  # pragma: no cover - httpx is a hard dependency
    HttpxConnectError = ()  # type: ignore[assignment]
    HttpxTimeoutException = ()  # type: ignore[assignment]

try:
    from openrouter.errors import NoResponseError, OpenRouterError
except ImportError:  # pragma: no cover - openrouter is a hard dependency
    NoResponseError = ()  # type: ignore[assignment]
    OpenRouterError = ()  # type: ignore[assignment]

_PROVIDER_MESSAGE_MAX_LEN = 500


class LlmError(Exception):
    """Base for every LLM-access failure.

    `code` and `retryable` are class attributes set by each subclass below.
    `str(exc)` is always the generic `LLM_FAILURE_MESSAGE` line (← D2); the
    real provider text, if any, lives in `.provider_message` for logs only.
    """

    code: ErrorCode
    retryable: bool

    def __init__(self, provider_message: str | None = None) -> None:
        self.provider_message = provider_message
        super().__init__(LLM_FAILURE_MESSAGE)


class LlmConfigurationError(LlmError):
    """Raised when the seam is misconfigured, before any client is built.

    Unchanged from sprint 01: no `code`, its own message naming the env
    var, not the generic line.
    """

    def __init__(self, message: str = "OPENROUTER_API_KEY is not set.") -> None:
        self.provider_message = None
        Exception.__init__(self, message)


class LlmAuthError(LlmError):
    code = ErrorCode.LLM_AUTH
    retryable = False


class LlmBudgetError(LlmError):
    code = ErrorCode.LLM_BUDGET
    retryable = False


class LlmRateLimitError(LlmError):
    code = ErrorCode.LLM_RATE_LIMIT
    retryable = True


class LlmTimeoutError(LlmError):
    code = ErrorCode.LLM_TIMEOUT
    retryable = True


class LlmRefusedError(LlmError):
    code = ErrorCode.LLM_REFUSED
    retryable = False


class LlmUnavailableError(LlmError):
    code = ErrorCode.LLM_UNAVAILABLE
    retryable = True


class LlmMalformedError(LlmError):
    code = ErrorCode.LLM_MALFORMED
    retryable = True


class LlmBadRequestError(LlmError):
    code = ErrorCode.LLM_BAD_REQUEST
    retryable = False


_STATUS_CODE_CLASSES: dict[int, type[LlmError]] = {
    400: LlmBadRequestError,
    404: LlmBadRequestError,
    413: LlmBadRequestError,
    422: LlmBadRequestError,
    401: LlmAuthError,
    402: LlmBudgetError,
    403: LlmRefusedError,
    408: LlmTimeoutError,
    524: LlmTimeoutError,
    429: LlmRateLimitError,
    500: LlmUnavailableError,
    502: LlmUnavailableError,
    503: LlmUnavailableError,
    529: LlmUnavailableError,
    200: LlmMalformedError,
}


def _redact(text: str) -> str:
    """Blank any literal occurrence of the configured OpenRouter API key.

    A real leak path, not a precaution: `OpenRouterDefaultError` inlines the
    raw response body into its own `.message`, and that body can echo back
    parts of the request. A blank configured key must not blank the whole
    string - `"".replace("", ...)` would otherwise turn every character
    boundary into the redaction marker.
    """
    key = get_settings().openrouter_api_key
    if not key:
        return text
    return text.replace(key, "[redacted]")


def _provider_message_of(exc: Exception) -> str | None:
    raw = getattr(exc, "message", "") or ""
    return _redact(raw)[:_PROVIDER_MESSAGE_MAX_LEN] or None


def _classify_status_code(status_code: int) -> type[LlmError]:
    exact = _STATUS_CODE_CLASSES.get(status_code)
    if exact is not None:
        return exact
    if 400 <= status_code < 500:
        return LlmBadRequestError
    return LlmUnavailableError


def classify(exc: Exception) -> LlmError | None:
    """Turn a caught exception into an `LlmError`, or `None` if it is not
    ours - the caller must re-raise the original exception unchanged in
    that case, never swallow it.
    """
    if isinstance(exc, LlmError):
        return exc

    if isinstance(exc, OpenRouterError):
        cls = _classify_status_code(exc.status_code)
        return cls(_provider_message_of(exc))

    if isinstance(exc, HttpxTimeoutException):
        return LlmTimeoutError(_provider_message_of(exc))

    if isinstance(exc, (HttpxConnectError, NoResponseError)):
        return LlmUnavailableError(_provider_message_of(exc))

    if isinstance(exc, (PydanticValidationError, OutputParserException)):
        return LlmMalformedError(_provider_message_of(exc))

    return None


def raise_for_finish_reason(message: BaseMessage) -> None:
    """Raise for a chat reply that finished as a refusal or a mid-stream
    provider error.

    Both arrive as ordinary, successful chunks (exit 0) with the failure
    visible only in `response_metadata["finish_reason"]` - there is no
    exception for `classify()` to catch, so this is the only way to detect
    them.
    """
    finish_reason = message.response_metadata.get("finish_reason")
    if finish_reason == "content_filter":
        raise LlmRefusedError()
    if finish_reason == "error":
        raise LlmUnavailableError()
