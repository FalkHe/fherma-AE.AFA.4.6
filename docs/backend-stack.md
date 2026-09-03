# Backend Stack — Motorcycle Buying Advisor
 
**Fixed constraints:** React frontend · PostgreSQL · user accounts · persistent,
resumable consultations · background ingestion · pushed progress · ULID keys.
 
---
 
## Stack
 
```
Python Backend
│
├── HTTP/API
│   ├── FastAPI
│   └── SSE (sse-starlette)
│
├── Models / validation
│   └── Pydantic 2
│
├── Configuration
│   └── pydantic-settings
│
├── Database
│   ├── PostgreSQL 16+
│   ├── pgvector
│   ├── SQLAlchemy 2 (async)
│   ├── psycopg 3
│   └── Alembic
│
├── Identity
│   └── python-ulid
│
├── Authentication
│   ├── pwdlib + Argon2
│   └── httpOnly session cookie + CSRF
│
├── CLI
│   └── Typer
│
├── Background jobs
│   ├── Taskiq
│   ├── Redis (broker)
│   └── Taskiq Admin              (optional, dev)
│
├── Realtime notification
│   ├── PostgreSQL LISTEN/NOTIFY
│   └── SSE
│
├── AI
│   ├── LangChain
│   ├── langchain-openrouter
│   ├── OpenRouter embeddings     (model via .env)
│   ├── LangGraph                 (only if a workflow requires it)
│   └── Pydantic structured outputs
│
├── AI observability
│   └── Langfuse                  (optional)
│
├── Prompts
│   ├── Markdown
│   └── Jinja2
│
├── Ingestion
│   ├── Web search API            (provider via .env)
│   ├── HTTPX
│   ├── trafilatura
│   └── Docling                   (only if sources are PDF)
│
└── Images
    └── Pillow
```
 
---
 
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
| psycopg 3 | Async driver; also carries LISTEN/NOTIFY |
| Alembic | Real user data means drop-and-reseed is unavailable |
| python-ulid | Sortable, opaque PKs; slugs are separate unique columns |
| pwdlib + Argon2 | Accounts required |
| Session cookie + CSRF | `EventSource` cannot send an `Authorization` header, so SSE needs cookie auth |
| Typer | Ingestion, embedding, backlog approval, admin bootstrap |
| Taskiq | 150-model ingestion is long-running; fan out per model |
| Redis | Taskiq broker; one small service, trivial local setup |
| Taskiq Admin | Dev-time queue inspection |
| LISTEN/NOTIFY | Fans events to every API worker; in-process buses do not |
| SSE | Push job progress and completion without polling |
| LangChain | Mandated; model wrappers, tools, retrievers |
| langchain-openrouter | Mandated LLM provider |
| LangGraph | Multi-step workflows, only when one is needed; resumability comes from chat history in PostgreSQL, not a checkpointer |
| OpenRouter embeddings | Model chosen via `.env`; model + dimensions stored per embedding, CLI re-embeds on change |
| Web search API | Search-then-fetch ingestion ("Suzuki GSR 600" → top ~5 results); provider via `.env` |
| Structured outputs | Reliable capture of firmness-tagged preferences |
| Langfuse | Traces the LLM calls of a turn; one callback handler. Tool calls are plain Python outside any Runnable, so they do **not** appear, and each call is its own root trace (no per-turn grouping) |
| Markdown + Jinja2 | Prompts out of source, iteration visible in diffs |
| HTTPX | Article fetching and any outbound API |
| trafilatura | Main-text extraction from article HTML |
| Docling | PDF parsing, only if the corpus needs it |
| Pillow | Ingest-time image variants, served as static files |
 
## Excluded
 
| Component | Why |
|---|---|
| Imagor | Solves dynamic resizing of user-supplied images; catalogue is fixed and variants are known |
| Scrapy | Enrichment is search-then-fetch, not crawling; Twisted does not fit an async app |
| RabbitMQ | Redis covers the broker role with less operational surface |
