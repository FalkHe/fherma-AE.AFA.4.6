---
phase: 5
step: "5.5"
title: Input-validation gap closure
summary: Close exactly the six audited validation gaps (filter parse caps, catalogue numeric filter bounds, page[number] upper bound, chat_id ULID shape, draft-spec extra/source_hints caps, login password max_length 1024) — nothing else; the ingestion warning policy stays pinned as-is.
effort: 3
dependencies: ["5.4"]
---

# Step 5.5 — Input-validation gap closure

**Effort: 3** — six well-located changes plus a curl matrix; the discipline
is in *not* sweeping further (the rest of the surface was audited and is
already bounded).

Binding contract: `docs/roadmap/phase-5/shared-knowledge.md` (D2 is the
exhaustive close-list — do not add items). Prior pins: Phase-1
shared-knowledge (login deliberately unvalidated — **relaxed for exactly one
bound by owner-approved OQ-A**, see item 6; nothing else about login moves),
Phase-2 error-shape split, Phase-4 filter semantics (`filter[manufacturer]`
unknown id matches nothing — keep). Agent: **backend-dev**. Zero deviations —
a deviation is a stop-and-report.

**Environment:** stack up (`make up`) for the live curl matrix; tests run
without it.

## Outline

1. `backend/app/api/jsonapi.py` `parse_filter`: cap comma-separated member
   count (proposal: 50) and per-member length (proposal: 128 chars);
   violation → 400 `invalid-filter` (the existing code, no new error code).
   Constants module-level next to `MAX_PAGE_SIZE`.
2. `backend/app/api/endpoints/catalogue_models.py`: `ge`/`le` bounds on the
   typed numeric filter params (`engineCcMin/Max`, `powerKwMin/Max`,
   `wetWeightKgMax`, `seatHeightMmMax`) mirroring the `SpecFilters`
   plausibility ranges in `app/llm/query_translation.py` (import/reuse, don't
   restate values). Junk/violation → FastAPI default 422 (typed-param pin).
   Note the landed 4.4 caveat: `SpecFilters`' own validators silently drop
   out-of-range bounds — the API-side bounds make that explicit at the edge;
   the service behaviour itself stays untouched.
3. `backend/app/api/jsonapi.py` `pagination()`: upper bound on `page[number]`
   (proposal: `le=10_000`) → default 422.
4. `backend/app/api/schemas/chat_messages.py`
   `ChatMessageCreateAttributes.chat_id`: constrain to ULID shape
   (`min_length=26, max_length=26` + Crockford-base32 pattern) → default 422.
   An unknown-but-well-formed id still answers 404 `not-found` (unchanged).
5. `backend/app/api/schemas/products.py` `DraftSpecRequest`: bound
   `extra`/`source_hints` (proposal: ≤ 50 keys, keys ≤ 64 chars, values
   serialized ≤ 2 000 chars — implement as a `@field_validator`) → default
   422 with `loc`.
6. `backend/app/api/schemas/auth.py` `LoginRequest.password`:
   `max_length=1024` (owner-approved OQ-A — caps Argon2 work per attempt).
   Violation → default 422; the 401-for-wrong-credentials behaviour and the
   username's normalise-only handling are unchanged; add no other login
   rule.

Tests: extend the existing endpoint/schema test files (the paired
`test_x.py`/`test_x_qa.py` convention); every new bound gets an
at-the-boundary pass case and an over-the-boundary failure case.

## Verification

- Suite + lint green.
- Live curl matrix (as admin where needed): oversized filter list → 400
  `invalid-filter`; `filter[engineCcMin]=999999` → 422; `page[number]=99999999`
  → 422; 27-char `chatId` → 422; giant `extra` dict → 422; a >1024-char login
  password → 422 while a wrong-but-sane one still answers 401; all previously
  valid requests still answer 200/201 byte-identically.
- `app openapi export` diff reviewed: bounds appear, no shape changes —
  **this opens S1** (frontend 5.14 regenerates types after this merges).

## Risks / notes

- Do not "improve" service-layer validation while here — the API edge is the
  scope; services already have their own invariants.
- Append cross-step decisions (`### Step 5.5`) to `shared-knowledge.md`,
  including the final constant values chosen — 5.17's curl matrix asserts
  them and 5.14 regenerates types against them.
