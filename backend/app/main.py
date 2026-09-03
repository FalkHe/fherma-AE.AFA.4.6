"""FastAPI application factory.

Started as `uvicorn app.main:create_app --factory`.
"""

import logging
import mimetypes
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.endpoints import (
    auth,
    catalogue_models,
    chat_messages,
    chats,
    documents,
    events,
    health,
    images,
    manufacturers,
    operations,
    products,
)
from app.api.endpoints.events import LISTENER_STATE_ATTRIBUTE
from app.api.jsonapi import JsonApiError, error_document, json_api_error_handler
from app.core.config import Settings, get_settings
from app.services.notification_listener import NotificationListener

logger = logging.getLogger(__name__)

# Never rendered to the client; kept generic so nothing derived from the
# exception (type, message, args) can leak into the response.
INTERNAL_ERROR_DETAIL = "An unexpected error occurred."

# The Vite dev server origin (both hostname spellings browsers may use);
# credentials are allowed because the SPA authenticates with a session cookie.
CORS_ALLOWED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Where the generated image variants are served from. Mirrors
# `app.api.schemas.images.MEDIA_URL_PREFIX`, which builds the URLs.
MEDIA_URL_PATH = "/media"

# The one media type the mount serves (the pinned image variants).
WEBP_MEDIA_TYPE = "image/webp"
WEBP_SUFFIX = ".webp"


def _configure_logging(settings: Settings) -> None:
    """Send standard Python logging to stdout at the configured level."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run one `app_events` listener for as long as this process serves traffic.

    The listener is started without waiting for the database: it reconnects on
    its own, so neither a slow nor a dead PostgreSQL can delay startup, and a
    listener outage costs live updates only — never liveness or readiness.
    """
    listener = NotificationListener()
    setattr(app.state, LISTENER_STATE_ATTRIBUTE, listener)
    listener.start()
    try:
        yield
    finally:
        await listener.stop()


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for anything a route or dependency didn't handle itself.

    The traceback goes to the server log only; the response carries a generic
    JSON:API error document with nothing derived from the exception (no type,
    message or args), so an internal failure never leaks implementation
    details to the client.
    """
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)
    document = error_document(500, "internal-error", INTERNAL_ERROR_DETAIL)
    return JSONResponse(status_code=500, content=document.model_dump())


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    _configure_logging(settings)

    app = FastAPI(
        title="Motorcycle Buying Advisor API",
        version=__version__,
        docs_url="/docs" if settings.environment == "development" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain failures of the JSON:API resources render as an error document;
    # request validation and the auth dependencies keep FastAPI's own bodies.
    app.add_exception_handler(JsonApiError, json_api_error_handler)
    # Anything else unhandled: generic JSON:API 500, traceback to the log only.
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(health.router)
    # Authentication is plain JSON and exempt from JSON:API, hence no /api.
    app.include_router(auth.router, prefix="/auth")
    # Plain SSE, not JSON:API, but part of the credentials-allowing /api surface.
    app.include_router(events.router, prefix="/api")
    app.include_router(catalogue_models.router, prefix="/api")
    app.include_router(chat_messages.router, prefix="/api")
    app.include_router(chats.router, prefix="/api")
    app.include_router(documents.router, prefix="/api")
    app.include_router(images.router, prefix="/api")
    app.include_router(manufacturers.router, prefix="/api")
    app.include_router(operations.router, prefix="/api")
    app.include_router(products.router, prefix="/api")

    _mount_media(app, settings)

    return app


def _mount_media(app: FastAPI, settings: Settings) -> None:
    """Serve the generated image variants as public static files.

    Product images are public per `docs/architecture.md`: no authentication, no
    CSRF, no JSON:API envelope — a browser must be able to put the URL in an
    `<img src>`.

    `check_dir=False` and no `mkdir`: building the application must have no
    filesystem side effects (it happens in tests and in `app openapi export`,
    where MEDIA_DIR is a container path that may not exist). The directory is
    created by `image_service` when the first image is stored; until then every
    media URL simply answers 404.
    """
    # Python 3.12's `mimetypes` has no `.webp` entry and the slim image ships no
    # /etc/mime.types, so every variant would be served as
    # application/octet-stream. The variants are WebP by contract.
    mimetypes.add_type(WEBP_MEDIA_TYPE, WEBP_SUFFIX)
    app.mount(
        MEDIA_URL_PATH,
        StaticFiles(directory=settings.media_dir, check_dir=False),
        name="media",
    )
