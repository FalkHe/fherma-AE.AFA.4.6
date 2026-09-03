#!/usr/bin/env bash
# Start the web container. Extra arguments are passed through to uvicorn.
set -euo pipefail

# The web container owns schema migration; the worker container never does.
# Kept out of the CMD so it also runs exactly once under `uvicorn --reload`.
echo "Running database migrations ..."
alembic upgrade head

exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 "$@"
