# Observability

## Application logging

Standard Python/Uvicorn logging to stdout, level from `LOG_LEVEL`. No
centralized logging stack, no Prometheus, no Sentry.

Job state is not a log concern: `operations` rows carry `status`, `progress`,
`message` and `error`, and the admin UI reads them over SSE. Operation messages
are English and rendered verbatim.

## Langfuse (optional)

`llm/models.py::observability_callbacks(settings)` returns `[]` unless
**all three** of `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`LANGFUSE_HOST` are non-empty. When they are, it constructs the `Langfuse`
client and returns `[CallbackHandler()]`, which `get_chat_model()` attaches.
Nothing else in the codebase knows about tracing.

**What it captures, precisely** — claim no more than this:

- Chat-model calls only. **Embeddings are never traced**: LangChain's embeddings
  emit no callback events.
- **Each LLM call is its own root trace.** There is no per-turn grouping, so a
  consultation turn appears as several unrelated traces.
- **Tool calls never appear.** They are plain Python outside any Runnable.

A Langfuse outage degrades to exporter warnings in the log; application
behaviour is unchanged.

## Running the local stack

Langfuse is packaged as a **separate compose file**, not a profile:

```bash
# in .env
COMPOSE_FILE=compose.yaml:compose.langfuse.yaml
```

```bash
make langfuse-up      # up -d langfuse-web langfuse-worker
make langfuse-down    # stop, by service name
```

`compose.langfuse.yaml` brings `langfuse-web` (port 3000), `langfuse-worker`,
its own `langfuse-postgres`, `clickhouse`, `valkey` and `minio`, and overrides
`app-web`/`app-worker` to point `LANGFUSE_HOST` at `http://langfuse-web:3000`
with keys taken from `LANGFUSE_INIT_PROJECT_*`. The stack self-provisions its
organisation, project, user and API keys from the `LANGFUSE_INIT_*` values in
`.env`; all `LANGFUSE_*` secrets must be set there (see `.env.dist`).

> **`make langfuse-down` uses `docker compose stop`, deliberately.** A
> service-scoped `docker compose --profile … down -v` once destroyed
> `postgres-data` — the application database — because `down` is never really
> service-scoped. Never run `down -v` in this repository.
