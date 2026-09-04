# Ingestion

Turns one typed name ("Suzuki GSR600") into review material: stored source
documents, a draft specification, an image, and embedded chunks — ending in
status `in_review`, waiting for an admin's approve/reject.

Ingestion is a Taskiq background job. The API/CLI only creates state and
enqueues; the worker executes and reports progress through the `operations`
table, which the admin UI watches over SSE.

## Module map

| Layer | Module | Responsibility |
|---|---|---|
| Enqueue | `services/product_service.py::start_ingestion` | Status transition → `operations` row → enqueue, in that pinned order |
| Job shell | `jobs/ingestion.py` | Worker session, failure/retry policy — nothing else |
| Orchestration | `services/ingestion/service.py` (`_Run`) | Stage sequence, milestones, warning policy, fresh-run semantics |
| Adapters | `ingestion/wikipedia.py`, `search.py`, `fetch.py`, `extract.py`, `storage.py`, `robots.py` | One external concern each; typed failures, never exceptions |
| LLM services | `spec_extraction_service.py`, `chunking.py`, `embedding_service.py` | Decide what the model reads / what gets embedded, write results |
| LLM plumbing | `llm/models.py`, `llm/embeddings.py`, `llm/extraction.py`, `llm/prompts.py`, `llm/fencing.py` | LangChain-over-OpenRouter factories, prompt loading, fencing |

`start_ingestion`'s order exists so a worker can never pick up a job whose
state is not yet visible: transition to `ingesting` (commits, announces
`product.updated`) → create `operations` row `queued` (commits) → enqueue
`ingestion.run(motorbike_id, operation_id)`. **Ids only** cross the process
boundary; Taskiq has no result backend, so `operations` is the sole shared
state.

Failure policy lives in the task shell: `TransientJobError` propagates and
`SmartRetryMiddleware` retries (3 attempts, delay × attempt with jitter,
capped at 60 s — not exponential); anything else calls `abandon()` — motorbike
back to `backlog`, operation `failed`, exception re-raised for the log.

## Stage sequence

Milestone wording and percentages are a contract — the admin UI renders these
messages verbatim.

| Progress | Message | Stage |
|---|---|---|
| 5 % | `Looking up Wikipedia` | Article + lead image |
| 15 % | `Searching the web` | Search provider → fetch candidates |
| 20–60 % | `Fetching sources (n/m)` | Fetch + extract + store each candidate |
| 65 % | `Processing images` | Download image, write variants |
| 80 % | `Extracting specifications` | LLM structured extraction → draft spec |
| 90 % | `Generating embeddings` | Chunk + embed stored documents |
| 100 % | succeeded | Motorbike → `in_review` |

```mermaid
sequenceDiagram
    participant R as _Run (worker)
    participant W as Wikipedia
    participant S as Search provider
    participant Web as Source sites
    participant L as OpenRouter (LangChain)
    participant DB as PostgreSQL + files

    R->>DB: discard previous run (rows + files; listing docs kept)
    R->>W: search title → article HTML → lead image + attribution
    R->>DB: store WIKIPEDIA document
    R->>S: 3 pinned queries (product / technical / magazine)
    S-->>R: candidate URLs + titles (never page content)
    loop each candidate (deduped by URL)
        R->>Web: fetch_html (20 s, 5 MiB, politeness gate)
        R->>R: trafilatura → normalized Markdown
        R->>DB: raw bytes to DATA_DIR + source_documents row
    end
    alt zero documents stored
        R->>DB: fail operation, motorbike → backlog (or retry if transient)
    end
    R->>Web: download lead image → variants to MEDIA_DIR
    R->>L: extraction prompt (fenced docs) → JSON-schema output
    R->>DB: upsert draft spec + merge identity
    R->>L: embed chunks (batches of 64)
    R->>DB: chunks + pgvector embeddings
    R->>DB: motorbike → in_review, operation → succeeded
```

**Fresh-run semantics.** Everything a previous run left behind is deleted
first — `source_documents` rows *and* their retained files, `motorbike_images`
rows *and* their variants — so a review screen never mixes two runs. Carve-out:
`listing` documents (used-price provenance) survive re-ingestion.

**Wikipedia (5 %).** Five pinned HTTP calls: REST search (limit 3; the matched
title is recorded as the disambiguation guard), article HTML through the shared
fetch layer, lead-image URL from the page summary, then a two-call attribution
chain (Action API `pageimages` + Commons `imageinfo/extmetadata`; `Artist` and
`Credit` are HTML and are stripped before storing, all-missing → `null`). The
article goes through the same extraction as every other source. Source type
`wikipedia` — the trust anchor downstream.

**Web search (15 %).** Search-then-fetch: a provider returns only `(url,
title)`; its copy of the page content is deliberately dropped because we fetch
every page ourselves for provenance and raw retention. Three pinned templates
run per model, and **the template decides the `source_type`** — a labelled
source mix without an LLM classifying pages:

| Query | `source_type` |
|---|---|
| `"{name}" motorcycle official specifications` | `product` |
| `"{name}" technical data specifications` | `technical` |
| `"{name}" review test` | `magazine` |

Top 2 per template, deduped by URL, capped at `INGESTION_MAX_WEB_DOCUMENTS`
(6). Additionally, up to 3 links claimed in `motorbikes.suggestion` become
fetch candidates *ahead of* provider results and up to 2 claimed type codes add
search terms — inputs only; the stored claim is never modified, and a
contradiction between claim and findings is a run warning.

**Fetch + extract + store (20–60 %).** Every outbound request goes through
`fetch.py::fetch_html`, so the limits live in one place: 20 s timeout, 5 MiB
ceiling enforced while the body streams, `text/html` only, redirects followed
(provenance records the post-redirect URL), honest `User-Agent`
(`MotorcycleBuyingAdvisor/0.1 (educational project)`), and a process-wide
`PolitenessGate` spacing same-host requests ≥ 1 s apart (search API hosts
included). The HTTP client is the `httpx2` distribution (`import httpx2`).
`extract.py` converts HTML to Markdown via trafilatura, with a heading-rescue
pass: when the first extraction keeps no ATX headings (Wikipedia REST HTML has
no article container), the body is re-extracted inside a synthetic `<article>`
wrapper — headings are what the chunker later splits on. `storage.py` retains
raw bytes forever at `DATA_DIR/sources/{motorbike_id}/{document_id}.html`.

**Image (65 %).** At most one image per run (the Wikipedia lead image),
downloaded through the shared client and gate. Variants `thumb` 320 / `card`
640 / `detail` 1280 px, WebP quality 80, aspect preserved, never upscaled, EXIF
orientation applied; allowlist `image/jpeg|png|webp|gif`. Variant paths are
never stored — they are derived from the image id. The row is committed
`pending`. A missing image is never a failure.

**Spec extraction (80 %) — first LLM call.** `spec_extraction_service` decides
what the model reads: Wikipedia first, each document head-truncated to 12 000
chars, total capped at `EXTRACTION_MAX_INPUT_CHARS`; `listing` documents never
reach the prompt. It also writes: `upsert_draft_spec` is a full-object replace
of the single `draft` row (the `verified` row is only ever written by
approval), then the identity block is merged into `motorbikes` — existing
non-NULL values win, type codes are unioned, variants only fill when empty, so
an admin's correction is permanent. `llm/extraction.py` owns the schema and
chain. A failed extraction is a warning: the admin fills the form by hand,
which is the correction mechanism anyway.

**Chunk + embed (90 %).** `chunking.py` does structural chunking only, two
LangChain splitters in sequence: `MarkdownHeaderTextSplitter` cuts at ATX
headings (`#`–`####`) and keeps the trail as `heading_path` ("Suzuki GSR600 >
Design", capped 512), then `RecursiveCharacterTextSplitter` cuts oversized
sections at `CHUNK_SIZE_CHARS`/`CHUNK_OVERLAP_CHARS`. Between the two stages
the paragraph break is restored: the header splitter joins a section's lines
with a Markdown hard break, which would otherwise deny the character splitter
its best boundary. Re-chunking is a
delete-and-rewrite that resets embeddings to NULL — rewritten text must never
keep the old vector. `embedding_service.py` embeds in batches of 64, one commit
per batch, measures every vector before writing, and guards
`EMBEDDING_DIMENSIONS` against the `vector(n)` column width; a mismatch raises
`DimensionMismatchError` naming the required migration. "Chunked but
unembedded" is a normal state — retrieval filters `embedding IS NOT NULL`.

**Completion.** Motorbike → `in_review` *before* the operation closes as
`succeeded`, so the backlog row flips in the same moment its progress cell
disappears. Warnings are kept: `Completed with warnings: …`.

## Prompts and the LLM seam

Prompts are version-controlled Markdown under `backend/app/llm/prompts/`
(`spec_extraction.md` for ingestion; `advisor_system.md`,
`query_translation.md`, `ping.md` belong to other paths). `llm/prompts.py`
renders them with Jinja2 + `StrictUndefined`, so a variable the template uses
but the caller did not pass raises instead of producing a prompt with a hole.
Autoescaping is off on purpose (Markdown to a model, not HTML to a browser).

**Ingestion contains no agentic tool calling.** `_Run` calls adapters in a
pinned order from Python; the model never decides what runs next. Which search
provider runs is configuration (`SEARCH_PROVIDER` → `get_search_provider()`
against the `SearchProvider` protocol) — a new provider is a class plus a config
value, never a change to the job. `OpenRouterSearchProvider` deliberately uses
raw httpx rather than the LangChain factory: the model there only carries the
web plugin; its prose is discarded and only `url_citation` annotations are read.

The extraction chain is exactly
`get_chat_model(model).with_structured_output(ExtractedSpec, method="json_schema")`
— constrained by schema, not asked nicely for JSON. `ExtractedSpec` mirrors
`motorbike_spec.SPEC_FIELDS` 1:1 plus the identity fields, vocabularies are
enums built from the ORM model, and every field is optional because "the
documents do not say" is the normal answer. Trust is deliberately low: each
field carries a `BeforeValidator` that normalises plausible output (pinned unit
table, decimal commas, text booleans) and **clamps anything implausible to
`None`** — a null the admin fills is cheaper than a wrong value they must first
notice. Two provider concessions live on the schema seam (all fields listed in
`required` with null unions; variant `specs` travel as `{key, value}` pairs and
are reshaped back).

Embeddings use LangChain's `OpenAIEmbeddings` as a protocol client with
`base_url` pointed at OpenRouter (langchain-openrouter ships no embeddings
class). `check_embedding_ctx_length=False` is mandatory — otherwise LangChain
sends token arrays that OpenAI-compatible gateways reject — and no `dimensions`
parameter is sent: the pinned model's native size matches the column by
migration, not by request-time parameter.

**Untrusted-text fencing.** Every fetched document is wrapped between
`<<<UNTRUSTED-DOCUMENT-START>>>` / `<<<UNTRUSTED-DOCUMENT-END>>>`, defined once
in `llm/fencing.py`. `fence()` strips marker look-alikes first, so a document
cannot close its own block and continue as instructions. See
[`../general/security.md`](../general/security.md).

## Error-handling policy

- **Adapters return typed failures, never raise** (`FetchFailure`,
  `WikipediaFailure`, `ExtractFailure`, `ExtractionFailure`,
  `EmbeddingFailure`) — only the orchestrator knows whether a missing source is
  a warning or the end of the run.
- **A partial failure is a warning**, appended to the operation message.
- **Zero usable documents is the one deterministic failure** → operation
  `failed`, motorbike → `backlog`.
- **Transient network causes raise `TransientJobError`** → broker retries the
  whole run, which is safe because a run is a fresh run.
- **`DimensionMismatchError` escapes loudly** — a deployment mistake naming its
  migration, never reduced to warning text.
- **The two LLM stages can never cost the run its documents** — review proceeds
  without a spec (admin fills the form) or without vectors (`app embeddings
  rebuild` backfills).
- Retries that exhaust are not reaped: a row can stay stuck in `ingesting`.

## Configuration

`.env`, full commented list in `.env.dist`.

| Key | Note |
|---|---|
| `OPENROUTER_API_KEY` | Missing → extraction and embeddings skip with a warning, run still succeeds |
| `SEARCH_PROVIDER` | `tavily` or `openrouter`. **Code default is `tavily`; `.env.dist` ships `openrouter`** |
| `TAVILY_API_KEY` | Needed by `SEARCH_PROVIDER=tavily`; empty is valid → Wikipedia-only + warning |
| `CHAT_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | Changing dimensions needs a migration altering `chunks.embedding`; the pass refuses to run until they agree |
| `CHUNK_SIZE_CHARS` (3200), `CHUNK_OVERLAP_CHARS` (400) | Chunking targets |
| `INGESTION_MAX_WEB_DOCUMENTS` (6), `INGESTION_FETCH_TIMEOUT_SECONDS` (20), `INGESTION_MAX_FETCH_BYTES` (5 MiB), `EXTRACTION_MAX_INPUT_CHARS` (60000) | Limits |
| `DATA_DIR`, `MEDIA_DIR` | Bind-mounted to `backend/var/{data,media}` (gitignored). `MEDIA_DIR` is served publicly read-only at `/media` |

**Provider cost.** Tavily free tier is 1000 credits/month, one credit per basic
query. OpenRouter's web plugin costs roughly $0.01–0.02 per query (≈ $4 per
1000 results plus the model tokens of the carrying call) — pick it when you
would rather not hold a Tavily key at all. Its cited URLs arrive tagged
`?utm_source=…`; that one parameter is stripped (all others kept) because the
URL is provenance and the dedupe key.

## Admin flow

Needs an admin account (`app users set-role <name> admin`).

1. Open `/admin` (backlog).
2. Add a model by name. `POST /api/products` creates the entry and enqueues the
   job, returning 201 with status **`ingesting`**; the row shows live progress
   over SSE.
3. The entry lands in `in_review`.
4. Review at `/admin/models/:motorbikeId` — tabs Identity, Documents, Specs,
   Image.
5. **Approve** promotes the draft specification to verified, approves pending
   images, and publishes the entry (`approved`). It requires a complete
   identity (manufacturer, model name, year-from) — otherwise 422
   `incomplete-identity`. **Reject** sets status `rejected` and deletes nothing;
   `rejected → ingesting` re-runs a fresh ingestion.

**Naming caveat:** Wikipedia's search matches noticeably better without spaces
— use "Suzuki GSR600", not "Suzuki GSR 600".

## CLI

Run in the live container (`docker compose exec app-web app …`) or, with the
stack down, a one-off `app-cli` container (`docker compose run --rm app-cli app
…`). `app <command> --help` documents every argument.

```bash
app ingest run "Suzuki GSR600"        # same as the UI action; enqueues, waits for nothing
app ingest probe "Suzuki GSR600"      # show which sources would be used, store nothing
app ingest fetch-url <url>            # fetch one page; Markdown to stdout
app ingest fetch-image <url> <bike-id>
app ingest extract-specs <slug> [--model <id>]   # re-run extraction from stored documents
app chunks rebuild [slug]             # delete + rewrite chunks (embeddings reset to NULL)
app embeddings rebuild                # enqueue a catalogue-wide re-embed
app llm ping | app llm embeddings-smoke
app jobs ping | app operations demo [--bike <slug>]
```

Identity and manufacturer maintenance (`app catalogue set-manufacturer |
set-identity | render-name | backfill-identity`) is documented in
[`model-naming.md`](model-naming.md).

**The worker does not hot-reload.** After changing ORM models or service code,
`docker compose restart app-worker`.

## Where things end up

| Artifact | Location |
|---|---|
| Raw fetched payloads | `DATA_DIR/sources/{motorbike_id}/{document_id}.html` (host `backend/var/data`) |
| Normalized Markdown + provenance (URL, title, type, fetch time) | `source_documents` |
| Draft specification | `motorbike_specs` (`kind = 'draft'`; approval promotes to `kind = 'verified'`) |
| Identity block | `motorbikes` (manufacturer FK, model name, years, type codes, variants) |
| Image variants | `MEDIA_DIR` (host `backend/var/media`), served at `/media/…` |
| Chunks + embeddings + `heading_path` | `chunks` (tsvector + pgvector columns) |
| Job state / progress | `operations` (streamed to the UI over SSE) |
