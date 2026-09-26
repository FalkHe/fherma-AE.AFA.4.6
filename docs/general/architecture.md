# Architecture

A high-level conceptual map: the guiding principle, the domain layers, the
system components, the deployment shape, the placement rules for the modular
trees, the wire convention and the session model. It is a map, not a spec —
routes, columns and payloads are pinned by the step specs. What the product is
for is [app-vision.md](app-vision.md); the data model is [model.md](model.md);
the vocabulary is [glossary.md](glossary.md); stack detail lives in the module
READMEs and in [backend-stack.md](backend-stack.md) /
[frontend-stack.md](frontend-stack.md).

Current state: the web application and the five-node game flow are implemented.
Where this document and the code disagree, the code wins.

## Guiding principle

The project proves knowledge of AI agents — prompting, RAG, tools, memory,
human-in-the-loop — not game design. Everything else stays minimal: the
smallest thing that makes the agent work and can be seen working.

**Single player only.** Multiplayer is a capstone candidate, and the data
model concedes exactly one thing to it: a `campaign_run_members` table as the
ownership root. The model also lets a user control several characters in one
campaign run; Stage-01 gameplay assumes one. Rolls carry a visibility flag
because hidden information is needed today, not because of multiplayer.

## The three domain layers

The separation is architectural, not stylistic:

- **Content** — campaigns, adventures, scenes and monster stat blocks as
  structured JSON. Structured lookups read JSON; they do not go through RAG.
- **Reasoning** — the LLM agent decides how a scene plays out.
- **Mechanics** — deterministic code: dice, hit points, state validation. The
  LLM never fakes a roll and never edits state directly; it calls a tool.

Only the SRD rules text is retrieved with RAG. None of these layers is built
yet; the boundary is stated here so nothing is built across it later.

## System components

None of these exist yet. They are listed so the boundaries between them are
fixed before anything is built.

**Character generation agent** — runs once at the start of a playthrough. The
player describes an idea in plain words; the agent asks a follow-up or two,
derives race, class and ability scores from the description with a little
randomness, generates a portrait through an image API and writes the character
sheet to state.

**Adventure content** — campaigns, adventures, scenes and definitions as
static JSON in git, pinned per run by content version. Content is
hand-authored, validated by `app content validate`, and reviewed as a diff.
Layout and scene fields are in [model.md](model.md).

**Rules knowledge base** — SRD 5.1 chunked into pgvector by a one-time ingest
CLI. Agentic: the game agent decides whether a lookup is needed and may
re-query.

**Game agent** — a five-node LangGraph flow: `advance` chooses one typed
effect, then `decide`, `execute`, `await_player` or `narrate` performs that
effect and returns control to `advance`. Checkpoint state contains active turn
and combat cursors, requests, results and narration progress; the database
contains durable facts and transcript history. `decide` may use only the
read-only `lookup_rule` (SRD RAG) and `recall_history` (semantic narration
memory) aids. All rolls and mutations run through deterministic
`playthrough.service` operations, and narration is an unbound call over public
evidence.

**Web client** — narration pane, state panel (HP, AC, inventory; turn order is
deferred — the DM-turn phase decides what a fight needs, and nothing tracks
turns before Stage 02), filtered agent trace with roll log and rule citations,
token and cost display, a campaign-run list, and a developer drawer (model,
temperature, system prompt, DM personality) kept separate from the player UI.

## Deployment shape

```
browser ──► frontend (Vite dev server, :5173)
   │
   └──────► app-web (uvicorn, :8000) ──► postgres (pgvector, :5432)
```

`app-web` runs `alembic upgrade head` and then uvicorn
(`docker/entrypoint-web.sh`). The `app-cli` / `node-cli` containers behind the
Compose `cli` profile reuse the same images, so lint and tests need no host
toolchain. Langfuse tracing talks to an external instance, configured by the
three `LANGFUSE_*` variables in `.env`; blank means off.

There is **no background job runner and no Redis.** Every operation is
request-scoped or a Typer CLI one-off. Anything that would once have been a
queued job is one of those two.

## Modular layout and its rules

Both trees are organised by **module**, not by technical layer: a module owns
its models, schemas, routes and service, and can be deleted without hunting
through six shared directories. The trees are summarised in `.claude/CLAUDE.md`;
each module states its own intent, surface and quirks in its `README.md`.

- **Promotion on evidence.** A helper or component earns a place in `core/` or
  `components/` only once a **second** module actually calls it, and only if it
  imports nothing from any of them. One caller means it lives in that caller's
  module and is promoted later, **unchanged**. Carve-out: the per-app
  singletons `core/` exists for — HTTP client, query-client factory, theme,
  i18n instance — are placed architecturally and may have one importer.
- **Module boundaries.** One module does not import another module's
  internals. Cross-module use goes through the other module's `service.py` or
  `models.py` — its public surface — and is stated explicitly in the step spec.
- **Services are modules of functions**, not classes. No repository classes and
  no ORM relationships: a query is a query. Services own the transaction
  boundary; `get_db_session` never commits; routes contain no `commit`, no
  `add`, no `execute`.
- **Call services through a module reference** — `from . import service`, then
  `service.create_user(...)`. This is contract, not taste: importing a service
  function by name rebinds it into the caller and the test suite's
  monkeypatching silently misses.
- **`frontend/src/api/schema.d.ts` is generated and committed, never
  hand-edited**, and no hand-written frontend type may stand in for a payload
  the backend does not send yet.

## Wire convention

Plain REST under `/api/v1`; resource objects are returned directly, with no
document envelope. The normative contract — paths, bodies, status codes, error
codes — is `docs/roadmap/phase-0/step-0.1.md` §5 and the exported
`frontend/openapi.json`. The conventions behind it:

- **camelCase on the wire**, produced by a shared Pydantic base, so there is
  no mapping code in either tree.
- **One error envelope**, `{"error": {"code", "message", "details"}}`, for
  every non-2xx response, including validation failures and the catch-all 500.
  `message` is English and server-side only; the frontend maps `code` to an
  i18n key with a fallback and never displays it.
- **Domain codes, not HTTP codes, carry meaning.** Failures sharing a status
  get different codes; failures that must be indistinguishable share one.

## Session model

Server-side sessions: no JWTs, nothing signed.

- The credential is an **opaque token, hashed at rest** (SHA-256), delivered in
  an **`HttpOnly`** cookie. A database dump yields no usable cookies; script
  cannot exfiltrate one; revocation is a `DELETE`.
- CSRF uses a **synchroniser token in a response header**, compared against the
  session row — never in a cookie or a body, so a cross-site page cannot read
  it, and comparing against the row avoids the double-submit cookie-injection
  weakness. The SPA keeps it in module memory only and re-acquires it from
  `GET /users/me` on each page load.
- **`SameSite=Lax` is correct across ports** — the port is not part of a site,
  so `:5173` → `:8000` is same-site. It is still cross-**origin**, which is why
  CORS (one allowed origin, `allow_credentials`, `X-CSRF-Token` in both
  `allow_headers` and `expose_headers`) and `credentials: "include"` are both
  mandatory. `Secure` is on only outside development.
- **One persona.** A single implicit `user` role, no role column; authorisation
  is ownership of a user id.
