# Implementation Roadmap — Motorcycle Buying Advisor

High-level, ordered phases. Each phase ends in something demonstrable. Detailed
slicing (file paths, agent assignments, step-by-step plans) is produced per
phase by the architect agent — this document deliberately stays above that.

Binding context: `docs/architecture.md`, `docs/backend-stack.md`,
`docs/frontend-stack.md`, `docs/core-requirements.md`.

---

## Agreed product decisions

Recorded from planning discussion (2026-08-26); these govern scope below.

- **Specs are LLM-extracted, admin-verified.** Ingestion always starts with
  Wikipedia as the first source, then web search focused on product sites,
  technical documentation and domain magazines (e.g. ADAC). Extracted specs
  are drafts until an admin approves them.
- **Backlog is a flag/status on the motorbikes table**, not a separate entity.
  Models enter the backlog two ways: an admin adds one manually, or the
  advisor flags a bike a customer mentioned that isn't in the catalogue yet.
- **Admin review happens in the admin UI**: fetched documents, extracted
  specs, and fetched images are reviewed and approved there before a model
  goes live. The CLI only bootstraps the first admin.
- **Product images are fetched during ingestion** (Wikipedia first —
  licence-friendly); the admin can reject/replace them in review.
- **Consultation is a guided interview**: the advisor deliberately interviews
  the customer (experience, use case, budget, physique …), captures
  firmness-tagged preferences, then recommends models. Free-form questions
  are allowed, but the agent steers.
- **Recommendations render as cards in the chat linking to model detail
  pages.** No dedicated comparison screen — comparisons happen
  conversationally via a tool call whose result renders in the chat.
- **Everything is behind login.** Open self-signup; roles `user`/`admin`;
  admin granted via CLI.
- **Four domain tools**: structured catalogue search, spec comparison,
  licence/fit checks (A2 compliance, rider fit), cost estimator.

---

## Phase 0 — Foundations

**Goal: both apps run locally via Docker Compose and talk to each other.**

- **0.1 Backend scaffolding** — FastAPI skeleton, PostgreSQL + pgvector,
   Alembic baseline, Typer CLI entry point, settings via `.env`,
   `/health` + `/ready`, Compose services (`app-web`, `postgres`, `redis`).
- **0.2 Frontend scaffolding** — Vite + React + TypeScript, Material UI theme
   (system/light/dark), React Router shell, TanStack Query, i18n bootstrap,
   OpenAPI type-generation pipeline (`app openapi export` → generated client).

*Done when:* `docker compose up` starts everything; the SPA loads and shows
backend health.

## Phase 1 — Accounts & access

**Goal: a person can register, sign in, and be made an admin.**

Two parallel tracks (backend `1.1 → 1.3 → 1.5`, frontend `1.2 → 1.4 → 1.6`)
with a single sync point: 1.6 needs 1.3. The binding contract for all steps is
`docs/roadmap/phase-1/shared-knowledge.md`; UI specs live in
`docs/roadmap/phase-1/ui-spec.md`.

- **1.1 Auth data model & services** *(backend)* — `users` + `sessions`
   tables, Alembic migration, `UserService`/`SessionService` (Argon2, hashed
   opaque session tokens, constant-time login, session revocation).
- **1.2 Auth screens, UI-only** *(frontend)* — login/registration forms with
   client-side validation against a stubbed `useAuth`; no backend needed.
- **1.3 Auth endpoints, cookies & CSRF** *(backend)* — `/auth/*` endpoints,
   session + CSRF cookies ("remember me"), `current_user`/`current_admin`/
   `csrf_protect` dependencies; freezes the OpenAPI surface.
- **1.4 Route guards & admin shell, UI-only** *(frontend)* —
   `RequireAuth`/`RequireAdmin` with the spinner pattern, empty admin area,
   role-conditional nav and sign-out UI.
- **1.5 CLI user commands** *(backend)* — `app users set-role` /
   `reset-password`; the first-admin bootstrap path.
- **1.6 Frontend auth wiring** *(frontend, sync point)* — regenerate API
   types, CSRF/401 client middleware, replace the stub, end-to-end
   login/register/logout.

*Done when:* register → login → see the (empty) app; CLI promotes the account;
admin section becomes visible only for that account.

## Phase 2 — Catalogue data & ingestion (admin side)

**Goal: an admin can put a motorcycle name into the backlog and end up with an
approved catalogue entry — documents, verified specs, image.**

Two parallel tracks, 21 steps of effort ≤ 4, two cross-track sync points
(S1: 2.15 needs 2.7; S2: 2.20 needs 2.17 + 2.9). The binding contract is
`docs/roadmap/phase-2/shared-knowledge.md`; UI specs live in
`docs/roadmap/phase-2/ui-spec.md`.

Backend track (`backend-dev`):
- **2.1 Catalogue domain models & services** — four tables, one migration,
   transition matrix, approval promotion (draft→verified).
- **2.3 JSON:API layer & `/api/products`** — the internal JSON:API layer +
   the products resource (freezes the S1 OpenAPI surface with 2.6).
- **2.5 Taskiq broker & worker service** · **2.6 Operations model/service/
   NOTIFY/API** · **2.7 SSE endpoint & LISTEN fan-out** *(merging 2.7 = S1)*.
- **2.9 Documents & images endpoints** — read-only provenance + image
   approve/reject.
- **2.10 Fetch & extract core** · **2.11 Wikipedia + web-search adapters** ·
   **2.12 Image pipeline (Pillow variants, `/media`)** ·
   **2.14 Ingestion orchestration job**.
- **2.16 LLM foundation (OpenRouter via LangChain)** ·
   **2.17 Spec extraction** *(merging 2.17 = S2)* ·
   **2.18 Chunks table & chunking** · **2.19 Embeddings & re-embed CLI**.

Frontend track (`frontend-dev`; 2.2/2.4/2.8/2.13 need zero backend code):
- **2.2 Admin UI spec** *(ui-ux-designer — done)* · **2.4 SSE client hook** ·
   **2.8 Backlog screen, UI-only** *(stubbed)* ·
   **2.15 Wire backlog live** *(S1)* ·
   **2.13 Review screen, UI-only** *(stubbed)* ·
   **2.20 Wire review live** *(S2)*.

- **2.21 Phase-2 acceptance run** *(qa)* — the done-criterion, end-to-end.

Commit per finished step; tag at the five milestones pinned in
`shared-knowledge.md` (M1 plumbing & shells → M2 live backlog → M3 real
ingestion → M4 review live & knowledge base → M5 acceptance) — each a point
where both tracks converge into something demoable.

*Done when:* admin types "Suzuki GSR 600", watches ingestion run, reviews and
approves it, and the model exists in the live catalogue with verified specs.

## Phase 2b — Manufacturers table (interlude)

**Goal: manufacturers become a first-class table (name, description, logo —
NULL for now) instead of a free-text column; extraction fills it; an
admin-only read API exposes it.** Admin UI for managing manufacturers is out
of scope. (Owner-requested refactor, 2026-08-27, before Phase 3 starts.)

Backend-only, 4 steps of effort ≤ 4. The binding contract is
`docs/roadmap/phase-2b/shared-knowledge.md`.

- **2b.1 Manufacturers table, migration & derived products attribute** —
   new table + FK, legacy column dropped, products wire shape preserved by
   derivation (zero frontend changes).
- **2b.2 Extraction fills the manufacturer + backfill CLI** — get-or-create
   on ingest; deterministic CLI backfills the 3 existing bikes without
   touching embeddings.
- **2b.3 `/api/manufacturers` read endpoints** — admin-only, read-only.
- **2b.4 Phase-2b acceptance run** *(qa)* — tags `phase-2b-done`.

*Done when:* the three approved bikes point at manufacturers rows, a fresh
ingest assigns its brand automatically, the products API is byte-compatible,
and the Phase-3 prerequisite (approved, embedded models) still holds.

## Phase 3 — Retrieval, the advisor agent & the consultation UI

**Goal: the advisory brain works end-to-end, and a customer can hold the
consultation in the browser.** (Re-sliced 2026-08-27: the consultation UI —
formerly step 4.1 — moved into this phase so each feature is built by
frontend and backend in parallel.)

Two parallel tracks, 17 steps of effort ≤ 4, two cross-track sync points
(S1: 3.6 needs 3.3 + 3.5; S2: 3.15 needs 3.13 + 3.14). The binding contract
is `docs/roadmap/phase-3/shared-knowledge.md`; UI specs live in
`docs/roadmap/phase-3/ui-spec.md`.

Backend track (`backend-dev`):
- **3.1 Chat persistence** — chats/messages/preferences tables (one
   migration), ChatService, firmness supersession.
- **3.3 Chat JSON:API endpoints** — chats + chat-messages resources incl.
   the frozen message-part contract *(with 3.5 = S1)*.
- **3.5 Minimal chat responder job** — plain-LLM replies via Taskiq,
   operation lifecycle, stale-turn healing, apologetic failure path.
- **3.7 Hybrid retrieval** — FTS + pgvector + RRF over the existing indexes,
   provenance-carrying results.
- **3.8 Query translation** · **3.9 RAG pipeline** — conversational language
   → retrieval queries + spec filters → candidate-scoped fused retrieval.
- **3.11 Domain tools I (convention, catalogue search, spec comparison)** ·
   **3.12 Domain tools II (licence/fit check, cost estimator)**.
- **3.13 Advisor agent loop** — guided interview, tool loop with limits,
   persisted tool calls/sources/recommendations *(with 3.14 = S2)*.
- **3.14 Preference capture & unknown-bike flagging**.
- **3.16 Scripted-conversation demo & prompt hardening**.

Frontend track (`frontend-dev`; 3.4/3.10 need zero backend code):
- **3.2 Consultation ui-spec** *(ui-ux-designer — done)* ·
   **3.4 Chat shell, UI-only** *(stubbed)* ·
   **3.6 Wire chat live** *(S1)* ·
   **3.10 Tool renderers, sources & recommendation cards, UI-only** ·
   **3.15 Wire advisor UI live** *(S2)*.

- **3.17 Phase-3 acceptance run** *(qa)* — the done-criterion, end-to-end.

Commit per finished step; tag at the five milestones pinned in
`shared-knowledge.md` (M1 chat plumbing & shells → M2 live chat → M3 the
RAG brain → M4 the advisor → M5 acceptance) — each a feature where both
tracks converge into something demoable.

*Done when:* a scripted conversation over the API yields a plausible
interview, visible tool calls, recommendations grounded in approved models,
and sources attached — and the same interview works in the browser with
seen/typing states, visible tool results, sources, and recommendation cards,
resumable after closing the browser.

## Phase 4 — Customer catalogue

**Goal: the browsable catalogue completing the customer experience.**

**Status: DONE (2026-08-28, tagged `phase-4-done`).** All steps landed and
QA-proven except 4.5, which was dropped/deferred: the pinned row-lock fix is
provably insufficient and any working fix changes a Phase-3 pin — owner
decision pending, see `docs/roadmap/phase-4/open-questions.md` OQ4.

Re-sliced 2026-08-28 into two parallel tracks (backend ∥ frontend, max
effort 4 per step, three milestones) — binding contract:
`docs/roadmap/phase-4/shared-knowledge.md`; UI:
`docs/roadmap/phase-4/ui-spec.md`.

- **4.1** *(superseded — moved into Phase 3; see
    `docs/roadmap/phase-4/step-4.1.md` for the mapping).*
- **4.2** *(split into 4.3–4.11; see `docs/roadmap/phase-4/step-4.2.md`
    for the mapping).*
- **4.3 Catalogue browse & image service reads** (backend) — browse query
    reusing the advisor's filter vocabulary, newest-approved-image read.
- **4.4 `/api/catalogue-models` endpoints** (backend) — customer-facing
    read-only resource (slim filtered/sorted list, self-contained detail);
    `GET /api/manufacturers` relaxed to signed-in users; opens S1.
- **4.5 Concurrent-turn 409 race fix** (backend) — *dropped/deferred: the
    pinned migration-free row lock provably cannot close the race
    (check-then-act spans commits); owner decision pending in
    `docs/roadmap/phase-4/open-questions.md` OQ4.*
- **4.6 Phase-4 UI spec** (design) — done at slicing time (`ui-spec.md`).
- **4.7 Catalogue list page on stubs** (frontend) — card grid,
    URL-persisted filter panel, pagination, nav entry.
- **4.8 Model detail page on stubs** (frontend) — gallery, grouped verified
    specs, article prose, out-of-chat Sources block.
- **4.9 Catalogue wired live + recommendation-card link** (frontend, S1) —
    real hooks, SSE invalidations, the `/catalogue/:motorbikeId` card link
    reserved in Phase 3.
- **4.10 Demo-script catalogue chapter** (docs).
- **4.11 Phase acceptance** (QA) — evidence run; tag `phase-4-done`.

*Done when:* a fresh user filters the catalogue, opens a model detail page
from a recommendation card, and an unapproved model is unreachable by direct
URL.

## Phase 5 — Hardening & submission

**Goal: grading-ready.**

Re-sliced 2026-08-28 into two parallel tracks (backend ∥ frontend, max
effort 4 per step, three milestones) — binding contract:
`docs/roadmap/phase-5/shared-knowledge.md`; UI:
`docs/roadmap/phase-5/ui-spec.md` (done at slicing time); open items:
`docs/roadmap/phase-5/open-questions.md`. The phase is deliberately
"confirm + test + close gaps" — landed failure states, progress indicators
and per-screen state handling are audited, not rebuilt.

- **5.1 / 5.2 / 5.3** *(split into 5.4–5.18; the step files remain as
    mapping markers)*.
- **5.4 Global 500 catch-all** (backend) — JSON:API envelope, code
    `internal-error`, no trace leak.
- **5.5 Input-validation gap closure** (backend) — the audited five gaps
    (filter caps, catalogue filter bounds, page cap, chat_id ULID shape,
    draft-spec dict caps); opens S1.
- **5.6 LLM client timeouts & transient mapping** (backend) — closes the
    step-3.9 stalled-embeddings finding.
- **5.7 Fencing module extraction** (backend, refactor) ·
    **5.8 Prompt-injection fencing on advisor surfaces** (backend) —
    retrieved chunks, preference values, query-translation context.
- **5.9 Langfuse callback factory** (backend; the phase's only new
    dependency + three `LANGFUSE_*` keys; opens with a compat spike) ·
    **5.10 Langfuse Compose profile** (backend; bonus, profile-gated).
- **5.11 Seed list & `app seed demo --auto-approve`** (backend) — real
    pipeline, skip-if-exists, report-and-continue.
- **5.12 Shared `UntrustedMarkdown` renderer** (frontend) + chat inertness
    test · **5.13 Error-surface gap closure + `AppErrorBoundary`**
    (frontend, per ui-spec) · **5.14 RegisterRoute tests + type refresh**
    (frontend, S1).
- **5.15 README: CLI reference, seed, Langfuse, limitations** (docs) ·
    **5.16 Grading map + demo-walkthrough submission chapter** (docs).
- **5.17 M1 security & error acceptance** (QA) · **5.18 Final acceptance &
    fresh-clone verification** (QA) — tags `phase-5-done`.

*Done when:* a fresh clone with only `.env` filled follows the README to a
seeded, hardened, documented app; the demo walkthrough replays green; the
grading map covers every criterion and claimed bonus.

## Phase 6 — Catalogue depth: researched identity & real prices

**Goal: the catalogue's own numbers are researched, not guessed or claimed —
identity (`docs/model-naming.md`) and market price both.**

Opened 2026-08-31 by the bulk-suggestion import (`app suggestions import`,
`backend/resources/bike-list.txt`): 200 proposed models now sit in the backlog
carrying **claims** — year ranges, manufacturer type codes, source links — in
`motorbikes.suggestion`. Nothing promotes those claims into catalogue data, and
nothing researches a price. This phase closes both gaps and folds in the
structured naming model the owner decided on 2026-08-31.

Sliced 2026-08-31 into two parallel tracks, 23 steps of effort ≤ 4, two
cross-track sync points and four milestones. The binding contract is
`docs/roadmap/phase-6/shared-knowledge.md`; UI specs live in
`docs/roadmap/phase-6/ui-spec.md`; open items in
`docs/roadmap/phase-6/open-questions.md`. The schema and rendering rationale
are `docs/roadmap/model-naming-data-model.md` and
`docs/roadmap/model-naming-display-spec.md` — their `N1`–`N9` slices are
**superseded** by the step numbers below (the merge those docs asked for has
happened; nothing runs twice).

Steps run in three blocks, in this order: **model changes → fencing →
ingestion.**

*Model changes* (backend, milestone M1) — schema and machinery, wired nowhere,
so the app stays byte-compatible with `phase-5-done`:
- **6.9 Refactor: `motorbikes.name` → `query_name`** — it is the phrase an
   admin typed, not a name; ships alone, zero behaviour change.
- **6.10 Identity columns & validators** — `buildingline`, `type_codes` (a
   *list* — one generation is known by several codes), `variants` (trims as
   spec deltas, never rows), with their caps and normalisation.
- **6.11 `naming_service`** — the parts→string escalation (buildingline →
   model → model + year range), rendered on the server, once.
- **6.12 Slug policy, `assign_identity` & the approval guard** — path-shaped
   `{manufacturer}/{model}/{year-range}`; an incomplete identity cannot be
   approved.
- **6.13 Used-price storage & staleness** — `motorbike_used_prices` (range,
   median, sample count, as-of date, per-source provenance) plus the
   `listing` source type. `msrp_eur`/`price_band` stay new-bike fields.

*Fencing* (backend, milestone M2) — carried from the 2026-08-31 injection
review, independent of everything else:
- **6.14 Fence the provenance metadata the model reads** — `source_title` and
   `heading_path` travel in the `retrieve_bike_knowledge` payload unfenced
   today, and both are attacker-controlled (the fetched page's own title and
   its own ATX headings). Fence and cap them payload-side; persisted JSONB
   stays byte-identical. Absorbs the former item 6.8, whose premise was
   refuted at slicing time (`heading_path` is already capped at 512 in the
   chunker and the column — no migration needed).

*Ingestion* (backend ∥ frontend, milestones M3 and M4):
- **6.15 Extraction writes the identity and the trims** — the year columns the
   backlog and catalogue already render stop being permanently NULL.
- **6.16 Manufacturer-name normalisation** — the suggestion list is a
   known-marque list; `Kawasaki Motors` becomes `Kawasaki`.
- **6.17 Suggested links & type codes as research input** — the fetch stage
   starts from `suggestion.links`, the codes become search terms, and a
   contradicted claim is a warning on the run, never a silent overwrite.
- **6.18 Identity backfill CLI & the approval CHECK constraint** —
   deterministic, never re-ingestion.
- **6.19 Resolution & rendering wired in** — type-code resolver leg, composite
   name sort, tools and both JSON:API resources render in context.
- **6.20 API identity block, variants & generated types** *(opens S1)*.
- **6.21 `listing` documents quarantined & the robots.txt gate** —
   re-ingestion must not wipe price provenance, and dated asking prices must
   never enter the knowledge base.
- **6.22 `app prices research` / `delete`** — used-price research over
   search-provider URLs through the landed fetch/extract pipeline.
- **6.23 The estimator uses the researched price** *(opens S2)* — used median
   first, with source and date named, and "indicative" when stale.

Frontend track (`frontend-dev`; 6.24–6.26 need zero backend code):
- **6.24 Review identity & claim-vs-finding, UI-only** — an admin approves an
   identity rather than trusting a list; a claim is never rendered as
   catalogue data anywhere a customer can see it.
- **6.25 Trims editor & customer trims block, UI-only** ·
   **6.26 Used-price blocks, UI-only** ·
   **6.27 Wire the admin surfaces live** *(S1)* ·
   **6.28 Wire the customer surfaces live** *(S2)*.

- **6.29 Docs** *(docs-writer)* · **6.30 M3 acceptance** *(qa)* ·
   **6.31 Final acceptance & fencing security proof** *(qa)* — tags
   `phase-6-done`.

Commit per finished step; tag at the four milestones pinned in
`shared-knowledge.md` (M1 model foundation → M2 fencing closed → M3
researched identity live → M4 researched prices) — each one a working
application. M1 and M2 are deliberately invisible: they change the schema and
the model-facing payloads without changing a single wire shape.

**A note on the price sources.** The roadmap originally named kleinanzeigen.de
as the primary source with mobile.de/autoscout24 as cross-checks, gated on a
robots/ToS review. That review was done at slicing time and **ruled out
purpose-built scrapers**: both sites' `robots.txt` disallow precisely the
price-filter, sort and search-parameter paths a sampler would need. What ships
instead reuses the landed search → fetch → extract pipeline over URLs the
search provider itself returned, honours `robots.txt` via the stdlib, and is
documented for what it is — a dated snapshot of *published* used prices with
visible sources, not a statistical sample of a classifieds database. Details
and the evidence: `shared-knowledge.md` D8.

**Hardening note.** 6.14 came out of a review of the Phase-5 injection work,
not the catalogue theme — it is here because Phase 6 is the general
optimisation phase. Fencing stays a mitigation, not a proof: the README's
"Known limitations" entry stands after it lands.

*Done when:* an imported suggestion, ingested from the admin backlog, ends up
with researched manufacturer, model name, year range and type codes that an
admin approved against the claim — and a used-price figure with a visible
source and date instead of a guess.

---

## Future upgrades

Not scheduled, not sliced — recorded so they are not rediscovered as surprises.

- **Variant-aware filtering.** With trims stored as `variants` JSONB deltas
  (owner decision 2026-08-31), `catalogue_search` / `SpecFilters` match the base
  row's `motorbike_specs` only. A hard filter for "≥ 15 l tank" excludes a model
  whose Adventure trim carries 20 l, and a `seat_height_mm ≤ 800` filter excludes
  a model that offers a low-seat trim — the base row is not the whole truth about
  the machine. The eventual fix needs three decisions together: matching
  `variants[].specs` in SQL (`jsonb_path_ops` GIN, or maintained min/max columns
  per filterable spec), a tool result that says *which* trim satisfied the
  filter, and an explicit "any trim matches" vs "the base matches" semantic.
  Sketched in `docs/roadmap/model-naming-data-model.md` §9.
- **Buildingline as a table.** It is a nullable text column on `motorbikes`
  today (owner decision: nothing points at a family, so a table buys integrity
  nobody consumes). Promote it — distinct values become rows, the column becomes
  an FK — if a facet UI, per-family content or an alias target ever ships.
- **Per-trim type codes.** Harley's model codes (`FLFB` vs `FLFBS`) really
  designate trims, and the flat `motorbikes.type_codes` list flattens that: a
  code resolves to the generation, not to the trim it names. The clean answer
  arrives with trim-aware filtering above — that is when a trim becomes
  addressable at all.
- **Alias table / alias metadata.** Deferred by the same decision. Manufacturer
  codes now resolve through `type_codes`; *spellings* ("R1300GS", marque
  abbreviations) still rely on the advisor normalising them, plus a resolver
  that absorbs case and punctuation. Build the `motorbikes.aliases` JSONB
  column when a transcript shows a real miss. Trigger list in the same doc §2.3.
- **Per-trim provenance and `model_years`.** No chunk, image or recommendation
  can be scoped to a trim, and per-year colours/packages/prices have no home.
  Neither is something the advisor needs today.

---

## Requirement coverage (grading)

| Requirement | Where it lands |
|---|---|
| LangChain + OpenRouter | Phases 2 (extraction, embeddings) & 3 (agent) |
| Advanced RAG (query translation, structured retrieval, chunking) | Phases 2 & 3 |
| ≥ 3 tool calls | Phase 3 (four tools) |
| React UI: sources, tool results, progress | Phases 2 (admin) & 3 (customer chat; catalogue in 4) |
| Error handling, validation, security | Phases 1, 5 (and throughout) |

Optional-task bonus (≥ 2 medium + 1 hard) covered by design: **hard** — hybrid
search; **medium** — user authentication & personalisation, prompt-injection
protection, logging/monitoring (Langfuse), real-time knowledge-base updates
(admin-triggered ingestion).
