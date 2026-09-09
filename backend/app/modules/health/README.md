# health

Liveness check for the API — lets orchestration and monitoring confirm the
service is up.

## Owns

- Nothing; stateless.

## Surface

- `GET` route returning `{"status": "ok"}`. See `frontend/openapi.json` for
  the exact wire shape.
