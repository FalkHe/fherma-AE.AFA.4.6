# Backend stack

**Fixed constraints:** React frontend · PostgreSQL · user accounts ·
persistent, resumable consultations · background ingestion · pushed progress ·
ULID keys · LLM access only through OpenRouter via LangChain.

Exact versions live in `backend/pyproject.toml` / `uv.lock`.

## Stack

```text
Python 3.12 backend
│
├── HTTP/API
│   ├── FastAPI
│   └── sse-starlette
│
├── Models / validation / config
│   ├── Pydantic 2
│   └── pydantic-settings
│
├── Database
│   ├── PostgreSQL 16 + pgvector
│   ├── SQLAlchemy 2 (async)
│   ├── psycopg 3
│   └── Alembic
│
├── Identity
│   └── python-ulid
│
├── Authentication
│   ├── pwdlib + Argon2
│   └── httpOnly session cookie + CSRF double-submit
│
├── CLI
│   └── Typer
│
├── Background jobs
│   ├── Taskiq (+ taskiq-redis)
│   └── Redis (broker only, no result backend)
│
├── Realtime notification
│   ├── PostgreSQL LISTEN/NOTIFY
│   └── SSE
│
├── AI
│   ├── LangChain
│   ├── langchain-openrouter        (ChatOpenRouter — chat models)
│   ├── langchain-openai            (OpenAIEmbeddings pointed at OpenRouter)
│   ├── openrouter                  (error types)
│   └── Pydantic structured outputs (method="json_schema")
│
├── AI observability
│   └── Langfuse                    (optional, gated on 3 env keys)
│
├── Prompts
│   ├── Markdown
│   └── Jinja2 (StrictUndefined)
│
├── Ingestion
│   ├── Search provider             (Tavily or OpenRouter web plugin, via .env)
│   ├── httpx2
│   ├── trafilatura
│   └── urllib.robotparser          (stdlib)
│
└── Images
    └── Pillow
```

## Justification

| Component | Why |
|---|---|
| FastAPI | React frontend needs an API tier |
| sse-starlette | Correct SSE headers and connection cleanup |
| Pydantic 2 | Request validation, tool I/O, structured LLM output |
| pydantic-settings | Typed config, trivial cost |
| PostgreSQL | Relational data and embeddings in one store |
| pgvector | Vector search co-located with the metadata that filters it |
| SQLAlchemy 2 async | Async ORM, matches FastAPI |
| psycopg 3 | Async driver; also carries LISTEN/NOTIFY on a dedicated connection |
| Alembic | Real user data means drop-and-reseed is unavailable |
| python-ulid | Sortable, opaque PKs; slugs are separate unique columns |
| pwdlib + Argon2 | Accounts required |
| Session cookie + CSRF | `EventSource` cannot send an `Authorization` header, so SSE needs cookie auth |
| Typer | Ingestion, chunking, embedding, identity backfill, seeding, snapshots, suggestion import, tool probes, user admin (15 sub-apps). Catalogue *approval* is UI-only |
| Taskiq | Bulk ingestion is long-running; fan out per model |
| Redis | Taskiq broker; one small service, trivial local setup |
| LISTEN/NOTIFY | Fans events to every API worker; an in-process bus does not |
| SSE | Push job progress and completion without polling |
| LangChain | Mandated; model wrappers, tools, splitters |
| langchain-openrouter | Mandated gateway — never the OpenAI API directly |
| langchain-openai | langchain-openrouter ships no embeddings class; `OpenAIEmbeddings` is used purely as an OpenAI-shaped protocol client against OpenRouter (`check_embedding_ctx_length=False` is mandatory) |
| Structured outputs | Spec extraction and query translation are schema-constrained (`json_schema`), not asked nicely for JSON |
| Two model keys | `ADVISOR_MODEL` for the consultation, `CHAT_MODEL` for utility calls, so interview quality is tunable without touching extraction |
| Langfuse | Traces the LLM calls; one callback handler. Tool calls are plain Python outside any Runnable so they do **not** appear, each call is its own root trace (no per-turn grouping), and embeddings emit no callback events |
| Markdown + Jinja2 | Prompts out of source; iteration visible in diffs |
| httpx2 | Article fetching and every outbound API call, behind one shared fetch layer |
| trafilatura | Main-text extraction from article HTML |
| urllib.robotparser | robots.txt gate for the used-price path — stdlib, no dependency |
| Pillow | Ingest-time image variants, served as static files |

## Excluded

| Component | Why |
|---|---|
| **LangGraph** | The advisor is a hand-rolled `bind_tools` loop with a step budget and timeout; resumability comes from chat history in PostgreSQL, not a checkpointer. Not a dependency |
| **Docling / PDF parsing** | PDFs are skipped with a warning; the corpus is HTML. Not a dependency |
| **Taskiq Admin** | `operations` rows plus SSE already expose job state to the admin UI; not worth a service |
| Imagor | Solves dynamic resizing of user-supplied images; the catalogue is fixed and variants are known |
| Scrapy | Enrichment is search-then-fetch, not crawling; Twisted does not fit an async app |
| RabbitMQ | Redis covers the broker role with less operational surface |

## Pins worth remembering

- `ListQueueBroker(..., socket_timeout=None)` — required with redis-py ≥ 8. Do
  not remove it and do not pin `redis<8`.
- `langchain~=1.0` downgrades `websockets` to 16.x. That is expected; don't
  "fix" it.
