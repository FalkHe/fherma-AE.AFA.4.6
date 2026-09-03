# Catalogue ingestion

How an admin turns a motorcycle name into an approved catalogue entry with
documents, a verified specification, and an image — through the UI and via
the CLI building blocks it's made of.

## Required configuration

Set these in `.env` (see `.env.dist` for the full, commented list):

- `OPENROUTER_API_KEY` — without it, spec extraction and embeddings skip with
  a warning instead of failing the run.
- `SEARCH_PROVIDER` — which web-search backend finds the product, technical
  and review pages: `tavily` (default) or `openrouter` (see below).
- `TAVILY_API_KEY` — needed by `SEARCH_PROVIDER=tavily`. Without it, ingestion
  runs Wikipedia-only (no web search) and appends a warning instead of failing.
- `CHAT_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` — model choice.
  Changing `EMBEDDING_DIMENSIONS` requires a migration that alters the
  `chunks.embedding` column width to match; the embedding pass refuses to run
  until they agree.
- `CHUNK_SIZE_CHARS`, `CHUNK_OVERLAP_CHARS` — chunking targets.
- `INGESTION_MAX_WEB_DOCUMENTS`, `INGESTION_FETCH_TIMEOUT_SECONDS`,
  `INGESTION_MAX_FETCH_BYTES`, `EXTRACTION_MAX_INPUT_CHARS` — ingestion
  limits.
- `DATA_DIR`, `MEDIA_DIR` — where raw fetched payloads and image variants are
  written inside the container (bind-mounted to `backend/var/data` and
  `backend/var/media` on the host, both gitignored). `MEDIA_DIR` is also
  served publicly, read-only, at `/media`.

## Web search providers

Both providers run the same three pinned queries (official specifications →
`product`, technical data → `technical`, review/test → `magazine`), return only
URL and title, and are switched by `SEARCH_PROVIDER` alone — the ingestion job
does not change. The pages themselves are always fetched by us.

- `tavily` (default) — `POST https://api.tavily.com/search`, basic depth, needs
  `TAVILY_API_KEY`. Free tier: 1000 credits/month, one credit per query.
- `openrouter` — OpenRouter's `web` plugin on the chat-completions endpoint;
  reuses `OPENROUTER_API_KEY` and `CHAT_MODEL`, so no second vendor account.
  Costs roughly $0.01–0.02 per query (web plugin results are billed at about
  $4 per 1000 results, plus the model tokens of the call that carries them) —
  noticeably more than a Tavily credit, so pick it when you would rather not
  hold a Tavily key at all. Cited URLs arrive tagged with
  `?utm_source=openai`; that parameter is stripped (all others are kept)
  because the URL is provenance and the dedupe key downstream.

Either way an empty key is a valid configuration: ingestion then runs
Wikipedia-only and appends a warning instead of failing.

## Admin UI flow

Requires an admin account (`docker compose exec app-web app users set-role
<name> admin` — see the root `README.md`).

1. Log in and open <http://localhost:5173/admin> (the backlog screen).
2. Add a model by name, e.g. "Suzuki GSR600". This creates the catalogue
   entry (`backlog` status) and enqueues an ingestion job; the row moves to
   `ingesting` and shows live progress over SSE.
3. Ingestion runs, in order: Wikipedia lookup (title + lead image) → web
   search for further sources (the configured provider, if it has a key) →
   fetch and store each document → download the image → LLM spec extraction
   into a draft → chunk
   and embed the stored documents. The entry lands in `in_review`.
4. Open the model's review screen (`/admin/models/:motorbikeId`) to check the
   fetched documents, the draft specification, and the image.
5. Approve promotes the draft specification to verified and the image to
   approved, and moves the entry to `approved` (published to the catalogue).
   Reject keeps the documents and draft (nothing is deleted) and returns the
   entry to the backlog, where ingestion can be retried.

**Naming caveat:** Wikipedia's search matches noticeably better without
spaces in the model name — use "Suzuki GSR600" rather than "Suzuki GSR 600".

## CLI building blocks

All commands run in the running `app-web` container (`docker compose exec
app-web app ...`) or, with the stack down, a one-off `app-cli` container
(`docker compose run --rm app-cli app ...`). `app <command> --help` documents
arguments and options in full.

```bash
# End-to-end, same as the UI's "add a model" action: creates the catalogue
# entry if needed and enqueues the full ingestion job. Nothing is waited for
# — follow it via `docker compose logs -f app-worker` or `GET /api/operations`.
docker compose exec app-web app ingest run "Suzuki GSR600"

# Show which sources ingestion would use for a name, without storing anything.
docker compose exec app-web app ingest probe "Suzuki GSR 600"

# Fetch one page in isolation; Markdown to stdout, progress to stderr.
docker compose exec app-web app ingest fetch-url https://en.wikipedia.org/wiki/Suzuki_GSR600

# Download one image for an existing catalogue entry (by id) and write its variant set.
docker compose exec app-web app ingest fetch-image <url> <motorbike-id>

# Re-run LLM spec extraction for one model from its already-stored documents
# (by slug). Replaces the draft only; the verified spec is untouched. This is
# the loop for tuning backend/app/llm/prompts/spec_extraction.md.
docker compose exec app-web app ingest extract-specs suzuki-gsr600 [--model <openrouter-id>]

# Re-chunk one model's stored documents, or every model's if the slug is omitted.
# Deletes and rewrites chunks, so their embeddings reset to NULL.
docker compose exec app-web app chunks rebuild [slug]

# Enqueue a full re-chunk and re-embed of every stored document (e.g. after
# changing CHUNK_SIZE_CHARS/CHUNK_OVERLAP_CHARS or the embedding model).
docker compose exec app-web app embeddings rebuild

# Sanity-check the OpenRouter connection.
docker compose exec app-web app llm ping
docker compose exec app-web app llm embeddings-smoke

# Prove the job queue loop works without touching ingestion.
docker compose exec app-web app jobs ping
docker compose exec app-web app operations demo [--bike <slug>]
```

## Where things end up

- Raw fetched documents: `backend/var/data` on the host (gitignored),
  normalized to Markdown and stored in Postgres alongside provenance
  (source URL, title, heading path).
- Image variants: `backend/var/media` on the host (gitignored), served
  read-only at `/media/...`.
- Chunks and embeddings: the `chunks` table (full-text + pgvector columns),
  rebuilt by `app chunks rebuild` / `app embeddings rebuild`.
