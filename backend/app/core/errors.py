from enum import StrEnum
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

from app.core.schemas import ErrorBody, ErrorEnvelope
from app.core.settings import get_settings

logger = structlog.get_logger()


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_AUTHENTICATED = "NOT_AUTHENTICATED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    CSRF_TOKEN_INVALID = "CSRF_TOKEN_INVALID"
    USERNAME_TAKEN = "USERNAME_TAKEN"
    ALREADY_STARTED = "ALREADY_STARTED"
    RUN_ARCHIVED = "RUN_ARCHIVED"
    CHARACTER_EXISTS = "CHARACTER_EXISTS"
    INVALID_RUN_STATUS = "INVALID_RUN_STATUS"
    ADVENTURE_ACTIVE = "ADVENTURE_ACTIVE"
    ADVENTURE_EXHAUSTED = "ADVENTURE_EXHAUSTED"
    EXIT_NOT_AVAILABLE = "EXIT_NOT_AVAILABLE"
    ROLL_NOT_USABLE = "ROLL_NOT_USABLE"
    INVALID_DC = "INVALID_DC"
    ACTION_NOT_AVAILABLE = "ACTION_NOT_AVAILABLE"
    ROLL_REQUIRED = "ROLL_REQUIRED"
    ALREADY_ACTED = "ALREADY_ACTED"
    OBJECT_NOT_REACHABLE = "OBJECT_NOT_REACHABLE"
    ITEM_NOT_CONSUMABLE = "ITEM_NOT_CONSUMABLE"
    HIT_NOT_USABLE = "HIT_NOT_USABLE"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    LLM_AUTH = "LLM_AUTH"
    LLM_BUDGET = "LLM_BUDGET"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_REFUSED = "LLM_REFUSED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_MALFORMED = "LLM_MALFORMED"
    LLM_BAD_REQUEST = "LLM_BAD_REQUEST"


# The player sees one generic line regardless of which LLM failure occurred;
# the code behind it is for us, not for them (← D2).
LLM_FAILURE_MESSAGE = "The AI service could not complete that request."


# status, message per code -- the complete table of step-0.1.md §5.1.
_ERROR_INFO: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.VALIDATION_ERROR: (422, "Request validation failed."),
    ErrorCode.NOT_AUTHENTICATED: (401, "Authentication required."),
    ErrorCode.SESSION_EXPIRED: (401, "Your session has expired. Please sign in again."),
    ErrorCode.INVALID_CREDENTIALS: (401, "Username or password is incorrect."),
    ErrorCode.CSRF_TOKEN_INVALID: (403, "CSRF token missing or invalid."),
    ErrorCode.USERNAME_TAKEN: (409, "That username is already taken."),
    ErrorCode.ALREADY_STARTED: (409, "This campaign run has already been started."),
    ErrorCode.RUN_ARCHIVED: (409, "This campaign run is archived and cannot be changed."),
    ErrorCode.CHARACTER_EXISTS: (409, "This campaign run already has a character."),
    ErrorCode.INVALID_RUN_STATUS: (409, "This campaign run's status does not allow that."),
    ErrorCode.ADVENTURE_ACTIVE: (409, "This campaign run already has an active adventure."),
    ErrorCode.ADVENTURE_EXHAUSTED: (409, "There is no adventure left to enter."),
    ErrorCode.EXIT_NOT_AVAILABLE: (409, "That exit is not available from here."),
    ErrorCode.ROLL_NOT_USABLE: (409, "That roll cannot be spent here."),
    ErrorCode.INVALID_DC: (409, "That difficulty is outside the allowed range."),
    ErrorCode.ACTION_NOT_AVAILABLE: (409, "That action is not available here."),
    ErrorCode.ROLL_REQUIRED: (409, "That check needs a roll."),
    ErrorCode.ALREADY_ACTED: (409, "This creature has already acted this turn."),
    ErrorCode.OBJECT_NOT_REACHABLE: (409, "That object is not reachable from here."),
    ErrorCode.ITEM_NOT_CONSUMABLE: (409, "That item cannot be used."),
    ErrorCode.HIT_NOT_USABLE: (409, "That hit cannot be used here."),
    ErrorCode.NOT_FOUND: (404, "Resource not found."),
    ErrorCode.METHOD_NOT_ALLOWED: (405, "Method not allowed."),
    ErrorCode.INTERNAL_ERROR: (500, "An unexpected error occurred."),
    ErrorCode.LLM_AUTH: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_BUDGET: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_RATE_LIMIT: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_TIMEOUT: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_REFUSED: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_UNAVAILABLE: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_MALFORMED: (502, LLM_FAILURE_MESSAGE),
    ErrorCode.LLM_BAD_REQUEST: (502, LLM_FAILURE_MESSAGE),
}

_HTTP_EXCEPTION_CODES: dict[int, ErrorCode] = {
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.METHOD_NOT_ALLOWED,
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode, *, details: dict[str, Any] | None = None) -> None:
        self.code = code
        self.status_code, self.message = _ERROR_INFO[code]
        self.details = details
        super().__init__(self.message)


def _envelope(code: ErrorCode, message: str, details: dict[str, Any] | None) -> dict:
    body = ErrorEnvelope(error=ErrorBody(code=code.value, message=message, details=details))
    return body.model_dump(by_alias=True)


def _clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        "session",
        path="/",
        samesite="lax",
        secure=settings.environment == "production",
    )


def register_error_handlers(app: FastAPI) -> None:
    # Function-local: core/llm/errors.py imports ErrorCode from this module
    # at module scope, so a module-scope import here would be a cycle.
    from app.core.llm.errors import LlmError

    @app.exception_handler(LlmError)
    async def _handle_llm_error(request: Request, exc: LlmError) -> JSONResponse:
        # `LlmConfigurationError` (sprint 01) has no wire `.code`: it fires
        # before any client is built, so it is an operator fault (a missing
        # server-side key), not something the caller did - it gets the
        # generic 500 envelope rather than one of the eight LLM_* codes, and
        # rather than crashing this handler. Expressed once, here, so any
        # future `LlmError` subclass that forgets to set `.code` degrades
        # the same way instead of raising `AttributeError`.
        code = getattr(exc, "code", ErrorCode.INTERNAL_ERROR)
        status_code, message = _ERROR_INFO[code]
        return JSONResponse(status_code=status_code, content=_envelope(code, message, None))

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        response = JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )
        # A dependency that raises has its injected `Response` discarded, so
        # this is the one place that clears the cookie on a failure path.
        if exc.code == ErrorCode.SESSION_EXPIRED:
            _clear_session_cookie(response)
        return response

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        code = ErrorCode.VALIDATION_ERROR
        status_code, message = _ERROR_INFO[code]
        details = {"fields": jsonable_encoder(exc.errors())}
        return JSONResponse(status_code=status_code, content=_envelope(code, message, details))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_EXCEPTION_CODES.get(exc.status_code, ErrorCode.NOT_FOUND)
        status_code, message = _ERROR_INFO[code]
        return JSONResponse(status_code=status_code, content=_envelope(code, message, None))

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled_exception", exc_info=exc)
        code = ErrorCode.INTERNAL_ERROR
        status_code, message = _ERROR_INFO[code]
        return JSONResponse(status_code=status_code, content=_envelope(code, message, None))
