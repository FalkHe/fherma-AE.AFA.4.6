---
phase: 6
step: "6.12"
title: "Slug policy, assign_identity and the approval guard"
summary: product_service.assign_identity becomes the single writer of the identity block with canonical slug recompute per D3; transition(..., APPROVED) gains IncompleteIdentityError mapped to 422 incomplete-identity; `app catalogue set-identity` is the first caller. No CHECK constraint (6.18 owns it) and no migration.
effort: 3
dependencies: ["6.11"]
---

# Step 6.12 — Slug policy, `assign_identity` and the approval guard

**Effort: 3** — one service function with careful collision/recompute
semantics, one guard with its API mapping, one CLI command, tests; no
migration and no schema change.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D2** — single
writer, full-object replace, announce; **D3** — slug shapes and the approved ⇒
canonical-slug invariant; **D4** — the guard now, the CHECK constraint **only
in 6.18** because today's approved rows would fail it) and
`docs/roadmap/model-naming-data-model.md` §3 (identity and slug), §4.2
(service changes). Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** stack up for the live CLI proof; head unchanged (no migration
here — a schema need is a stop-and-report). The 200-row imported backlog is
the test corpus: pick a row from it, do not invent names.

## Outline

- `backend/app/services/product_service.py`:
  - **new** `class IncompleteIdentityError(Exception)` carrying the missing
    field names in its message;
  - **new** `async def assign_identity(session, motorbike, *, manufacturer_id, buildingline, model_name, year_from, year_to, type_codes, variants) -> Motorbike` —
    the **only** writer of the identity block (D2): passes `buildingline`
    through `normalise_buildingline`, runs `identity_validation.normalize_type_codes`
    / `normalize_variants` and `logger.warning`s each dropped entry (callers
    needing run-visible warnings — 6.15 — validate first and pass clean lists),
    full-object replace of all seven fields, recomputes the slug, commits,
    `_announce`s `product.updated`;
  - slug recompute (D3): when `manufacturer_id`, `model_name` and `year_from`
    are all set, the canonical slug is
    `f"{manufacturer.slug}/{slugify(model_name)}/{year_from}-{year_to or ''}"`
    (manufacturer resolved by id — an unknown id is a `ValueError`); with an
    incomplete identity the existing slug is left untouched (a backlog row
    keeps `slugify(query_name)`). A recompute colliding with another row's
    slug raises the existing `DuplicateModelError` **before** anything is
    written;
  - `transition(...)`: before the `LEGAL_TRANSITIONS` matrix applies its side
    effects — i.e. as a new guard at the top of the `APPROVED` branch — raise
    `IncompleteIdentityError` when `manufacturer_id`, `model_name` or
    `year_from` is NULL (D4).
- `backend/app/api/endpoints/products.py`: in `update_product`'s transition
  `try`, catch `product_service.IncompleteIdentityError` →
  `jsonapi.JsonApiError(status_code=422, code="incomplete-identity", detail=str(error))`,
  mirroring the `invalid-transition` mapping beside it. No new writable
  attributes — the PATCH `identity` block is 6.20.
- `backend/app/cli/catalogue.py`: new command `set-identity`
  (`app catalogue set-identity <slug> --manufacturer "BMW" --model-name "R 1250 GS" --year-from 2019 [--year-to 2023] [--buildingline GS] [--type-code K50 …] [--variants-json '[]']`):
  resolves the row by slug (`_fail` when unknown), gets-or-creates the
  manufacturer, parses `--variants-json` (default `[]`; invalid JSON →
  `_fail`), calls `assign_identity`, echoes the new slug;
  `DuplicateModelError` → `_fail`.
- Tests: `backend/tests/services/test_product_service.py` — assign_identity
  full-replace + canonical slug, provisional slug kept on incomplete identity,
  `DuplicateModelError` on collision, announce called, approval guard raising
  per missing field and passing when complete;
  `backend/tests/api/test_products.py` — PATCH to `approved` on an identity-less
  `in_review` row returns 422 with `code == "incomplete-identity"`;
  `backend/tests/cli/test_catalogue.py` — set-identity happy path, unknown
  slug, bad `--variants-json`.

## Verification

- `make backend-test` + `make lint` green.
- Live CLI proof on one imported-backlog row:
  `docker compose run --rm app-cli app catalogue set-identity <its-slug> --manufacturer "BMW" --model-name "R 1250 GS" --year-from 2019 --year-to 2023`,
  then `docker compose exec postgres psql -U app -d application -c "SELECT slug FROM motorbikes WHERE model_name = 'R 1250 GS'"`
  shows `bmw/r-1250-gs/2019-2023`; `app catalogue render-name <that-id>` now
  prints the structured name (6.11's CLI, first time off the fallback).
- The 422 guard is proven by the API test — a live approve needs an
  `in_review` row and belongs to the M1 demo / QA 6.30, not here.

## Risks / notes

- **No CHECK constraint and no migration in this step** — 6.18 adds it after
  the backfill (D4's stated reason: today's approved rows would fail it on
  day one). Resist the temptation.
- Guard order: `LEGAL_TRANSITIONS` fires first, so only an `in_review` row can
  ever see `incomplete-identity` — intended, note it in the test.
- 6.15 (extraction), 6.18 (backfill CLI) and 6.20 (API PATCH) all call
  `assign_identity`; its keyword signature and the "incomplete keeps the old
  slug" rule are frozen once landed. The three seeded approved rows keep their
  flat slugs until 6.18 — the D3 invariant is only enforceable after the
  backfill.
- Append (`### Step 6.12`) to `shared-knowledge.md`: the assign_identity
  signature, the incomplete-identity error code, and the "callers wanting run
  warnings validate first" convention for 6.15.
