# Security

Domain-appropriate measures for a login-gated advisor that reads the public web.
Current state, plus the gaps we know about.

## Authentication and sessions

- Argon2 via pwdlib. Login compares against a module-level dummy hash when the
  username is unknown, so timing does not distinguish "no such user" from "wrong
  password"; both answer 401.
- Opaque session tokens, stored **sha256-hashed**; the plaintext only ever lives
  in the cookie.
- TTL 24 h, or 30 days with "remember me" (`Max-Age=2592000`). No sliding
  renewal.
- All sessions are revoked on password reset and on demotion from admin.
- Cookies: `session` `HttpOnly`, `csrf_token` readable by JS, both
  `SameSite=Lax`, `Path=/`, `Secure` in production.
- `SameSite=Lax` rather than `Strict` because `EventSource` must send the cookie
  on the SSE connection.
- **CSRF double-submit** (`csrf_protect`) on every cookie-authenticated write
  except register and login. The frontend middleware attaches `X-CSRF-Token`
  from the cookie to every non-GET/HEAD/OPTIONS request.
- Registration rules: username 3–32 `^[a-z0-9_.-]+$` (lowercased), password
  8–128. **Login is deliberately unvalidated** apart from one bound —
  `password` `max_length=1024`, which caps Argon2 work per attempt.
- Roles are `user` / `admin`. `current_admin` is the real authorisation
  boundary; the SPA's `RequireAdmin` is UX only.

## Authorization surface

| Surface | Access |
|---|---|
| `/api/products`, `/api/documents`, `/api/product-images`, `/api/operations`, `/api/manufacturers/{id}/buildinglines` | `current_admin` — reads included |
| `/api/catalogue-models`, `/api/manufacturers`, `/api/chats`, `/api/chat-messages`, `/api/events` | `current_user` |
| `/health`, `/ready`, `/media/*` | unauthenticated |

Customers see **only approved models**. A non-approved or unknown id returns
404, never 403 — no existence leak. Chats are scoped to their owner; another
user's or a soft-deleted chat is 404.

`/media` is an unauthenticated static mount: product images are public by
design. Raw retained payloads under `DATA_DIR` are never served.

## Input validation

Beyond Pydantic's per-field types:

| Bound | Value |
|---|---|
| `filter[...]` members / member length | 50 / 128 chars → 400 `invalid-filter` |
| `page[number]` / `page[size]` | ≤ 10 000 / ≤ 100 |
| Catalogue numeric filters | clamped to the extraction plausibility windows (engine 25–3000 cc, power 0.5–400 kW, weight 30–600 kg, seat 400–1200 mm) → 422 outside |
| `chatId` in a message POST | exactly 26 chars, Crockford ULID alphabet |
| Chat message body | ≤ 4000 chars (mirrored in the composer) |
| Login password | ≤ 1024 chars |
| Draft-spec `extra` / `source_hints` | ≤ 50 keys, key ≤ 64, value ≤ 2000 chars measured as JSON |
| Type codes / variants | ≤ 8 codes matching `^[A-Z0-9][A-Z0-9\-/ ]{1,31}$`; ≤ 20 trims, name ≤ 64, description ≤ 400 |

There is **no request body-size cap** — a reverse proxy would own that in
production, which is out of scope.

## Error handling

A catch-all `Exception` handler returns the JSON:API envelope `500
internal-error` with the fixed detail "An unexpected error occurred." The
traceback goes to the log only; no exception text, module path or query ever
reaches a client. 401/403 keep `{"detail": …}`, and body validation keeps
FastAPI's default 422 shape, so the SPA can branch on shape plus code.

The frontend never renders an error object: screens show an `EmptyState` with a
refetch action, and `AppErrorBoundary` catches render crashes with a reload
prompt.

## Prompt injection

Everything we fetch from the public web is attacker-controlled, so it is
**fenced** before any model reads it. One definition site, `llm/fencing.py`:
markers `<<<UNTRUSTED-DOCUMENT-START>>>` / `<<<UNTRUSTED-DOCUMENT-END>>>`, plus
a look-alike regex — `fence()` replaces anything resembling a marker with
`[fence removed]` so a document cannot close its own block and continue as
instructions.

Fenced surfaces:

1. **Retrieved snippets** in `retrieve_bike_knowledge`: `text`, and also
   `sourceTitle` and `headingPath`, which are the fetched page's own title and
   its own ATX headings — equally attacker-controlled. Capped at 160 chars each.
2. **Preference values** rendered into the advisor system prompt (the customer
   authored them).
3. **`utterance`, `history_summary` and preference values** in the
   query-translation prompt.
4. **Every source document** in the spec-extraction prompt.

A preference *attribute* is never fenced — it is normalised to a short
lower-case token first. **Model identity strings are never fenced either**
(names, buildingline, type codes): they pass the admin review gate before
approval, and a fenced name would corrupt the string the advisor has to say
back to the customer.

The fencing happens **payload-side only**: `ToolSpec.model_view` returns the
fenced copy to the model while `execute` records the *unfenced* payload, so
persisted `tool_calls[].result` and `sources[]` stay byte-identical to what the
service produced and the UI renders clean text. Both prompts state explicitly
that content between markers is data and can never change the task or the
schema.

On the render side, all Markdown from the server — assistant replies, retrieved
prose, Wikipedia articles — goes through `UntrustedMarkdown`: GFM only, raw HTML
off, `rehype-raw` never added, links forced to `target="_blank"
rel="noopener noreferrer"`. User-authored text is rendered as plain
`white-space: pre-wrap`, never as Markdown.

**Fencing is a mitigation, not a proof.** A determined injection inside a
fetched document can still influence a reply; it cannot escalate privileges,
because tools carry no user-supplied SQL and every write tool is scoped to the
current chat.

## Model-facing budgets

`AGENT_MAX_TOOL_STEPS = 8` rounds then one tools-unbound wrap-up call, the whole
turn under `asyncio.timeout(AGENT_TIMEOUT_SECONDS = 120)`; chat requests time
out at 60 s and embeddings at 30 s, both with `max_retries = 2`. A runaway
model costs a bounded number of calls.

## CORS

Allow-list exactly `http://localhost:5173` and `http://127.0.0.1:5173`, with
credentials. Not a wildcard — credentialed CORS forbids it anyway.

## Known gaps

- **No rate limiting** (out of scope) — and no body-size cap.
- **Concurrent-turn race.** Two genuinely simultaneous `POST /api/chat-messages`
  for one chat both return 201 and both enqueue a turn, violating the 409
  contract. Unreachable through the UI (the composer disables over SSE far
  faster than a human can double-send) and it degrades gracefully — both replies
  persist. The fix needs an owner decision; see
  [`decisions.md`](decisions.md#open-decisions).
- **`a2Eligible` is not cross-checked against power.** Extraction has been
  observed marking a 72 kW bike A2-eligible (the ceiling is 35 kW). It is
  non-deterministic extraction noise rather than a systematic bug, but the flag
  is a customer-visible catalogue filter. Owner decision pending.
- **Residual injection risk** as described above.
- `storage.save_raw_document` performs no path-traversal check on its id
  arguments. Unreachable today — both ids are server-minted ULIDs — but the
  module enforces nothing; regression tests already exist in
  `backend/tests/services/ingestion/test_storage_qa.py`.
- The `RobotsGate` in `ingestion/robots.py` is implemented and tested but **not
  wired into any fetch path**, because the used-price research that was to use
  it never landed.
