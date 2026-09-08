from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.settings import get_settings


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    docs_url = "/docs" if settings.environment == "development" else None
    openapi_url = "/openapi.json" if settings.environment == "development" else None

    app = FastAPI(
        title="AI Dungeon Master API",
        version="0.1.0",
        docs_url=docs_url,
        openapi_url=openapi_url,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        expose_headers=["X-CSRF-Token"],
    )

    register_error_handlers(app)

    app.include_router(api_router, prefix="/api/v1")

    return app
