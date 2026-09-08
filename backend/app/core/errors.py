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
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# status, message per code -- the complete table of step-0.1.md §5.1.
_ERROR_INFO: dict[ErrorCode, tuple[int, str]] = {
    ErrorCode.VALIDATION_ERROR: (422, "Request validation failed."),
    ErrorCode.NOT_AUTHENTICATED: (401, "Authentication required."),
    ErrorCode.SESSION_EXPIRED: (401, "Your session has expired. Please sign in again."),
    ErrorCode.INVALID_CREDENTIALS: (401, "Username or password is incorrect."),
    ErrorCode.CSRF_TOKEN_INVALID: (403, "CSRF token missing or invalid."),
    ErrorCode.USERNAME_TAKEN: (409, "That username is already taken."),
    ErrorCode.NOT_FOUND: (404, "Resource not found."),
    ErrorCode.METHOD_NOT_ALLOWED: (405, "Method not allowed."),
    ErrorCode.INTERNAL_ERROR: (500, "An unexpected error occurred."),
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
