# Backend image: FastAPI app, Typer CLI (and later the Taskiq worker).
# Build context is the repository root.
FROM python:3.12-slim

# uv provides dependency installation from the committed lock file.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /usr/local/bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    # Keep the virtualenv outside /app so the dev bind mount cannot shadow it.
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first: this layer is cached until the lock file changes.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-install-project

COPY backend/ ./
RUN uv sync --locked

COPY docker/entrypoint-web.sh /usr/local/bin/entrypoint-web.sh
RUN chmod +x /usr/local/bin/entrypoint-web.sh

EXPOSE 8000

# Arguments given to the container are appended to the uvicorn command
# (Compose passes `--reload` in development).
ENTRYPOINT ["/usr/local/bin/entrypoint-web.sh"]
