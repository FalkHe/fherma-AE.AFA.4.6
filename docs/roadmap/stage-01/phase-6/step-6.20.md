---
phase: 6
step: "6.20"
title: API identity block, variants and the generated types
summary: Additive buildingline/typeCodes/variants/queryName/suggestion on the admin products resource, a writable identity block on PATCH through assign_identity, variants on the catalogue-models detail, the buildinglines read endpoint, and the committed generated client. Opens sync point S1.
effort: 3
dependencies: ["6.19"]
---

# Step 6.20 — API identity block, variants and the generated types

**Effort: 3** — schema and endpoint work against fully pinned shapes
(ui-spec §8 API-1/2/5/6), one generated artifact, no new service logic.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (**D6** —
`suggestion` on the admin resource only, never on `catalogue-models`; pinned
wire shapes stay additive; D2 — the PATCH writes through `assign_identity`
and nothing else) and `docs/roadmap/stage-01/phase-6/ui-spec.md` §8 (API-1, API-2,
API-5, API-6 — the frontend is built against these names). Detail: data-model
§6 (API rows). Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** stack up for the curl checks. No worker restart (API only).
**This step opens sync point S1**: frontend 6.27 starts only after this step
is merged with the regenerated client committed. The change is additive by
contract — if `pnpm typecheck` breaks on the regenerated types, this step
violated the additive rule; fix the schema, never the frontend.

## Outline

- `backend/app/api/schemas/products.py`:
  - `ProductAttributes` gains (additive): `query_name: str`,
    `buildingline: str | None`, `type_codes: list[str]`,
    `variants: list[ProductVariant]`, `suggestion: ProductSuggestion | None`.
    `name` keeps its key (rendered since 6.19); `slug` is now path-shaped —
    same key, same type.
  - **New** `ProductVariant(JsonApiModel)`: `slug: str`, `name: str`,
    `description: str | None`, `specs: dict[str, Any] | None` (the delta;
    keys stay the snake_case frozen spec names — they are data, not schema
    fields).
  - **New** `ProductSuggestion(JsonApiModel)` — the claim JSONB typed so the
    aliasing camelCases it (ui-spec API-1): `source: str`, `raw: str`,
    `manufacturer: str | None`, `model: str | None`, `year_from: int | None`,
    `year_to: int | None`, `in_production: bool`,
    `year_ranges: list[SuggestionYearRange]` (`from`/`to` — use
    `Field(alias="from")` on a `from_` field), `type_codes: list[str]`,
    `links: list[str]`. Unknown keys ignored, never rejected — it is stored
    JSON.
  - **New** `IdentityRequest(JsonApiModel, extra="forbid")` —
    `manufacturer_id: str | None`, `buildingline: str | None` (≤ 64),
    `model_name: str | None` (≤ 128), `year_from: int | None`,
    `year_to: int | None` (each `1885 ≤ y ≤ current year + 2`, pair order
    checked), `type_codes: list[str]`, `variants: list[…]` — boundary caps
    reusing 6.10's validator models (do not restate the regex/caps).
    `ProductPatchAttributes` gains `identity: IdentityRequest | None`.
- `backend/app/api/endpoints/products.py` — `update_product`: when
  `identity` is present, verify `manufacturer_id` exists (unknown → 422 with
  a field pointer), call `product_service.assign_identity(...)` (full-object
  replace — the SPA sends the whole block), and render from the reloaded row
  so the response carries the recomputed `slug`. `DuplicateModelError` → the
  landed 409 `duplicate-model`; `IncompleteIdentityError` on an approval
  PATCH already maps to 422 `incomplete-identity` (6.12 — do not re-map).
  List/detail serialise the new attributes; `suggestion` comes straight off
  the row.
- `backend/app/api/endpoints/manufacturers.py` + `schemas/manufacturers.py` —
  ui-spec API-5: `GET /api/manufacturers/{manufacturer_id}/buildinglines`
  (admin-authed like the rest of the router) returning the distinct values
  via 6.10's `list_buildinglines`; shape: `{"data": ["GS", "RT", …]}`.
- `backend/app/api/schemas/catalogue_models.py` + endpoint —
  `CatalogueModelAttributes` (detail **only**) gains
  `variants: list[ProductVariant]` (same wire model; import or duplicate per
  the layering rule, but one shape). The list resource gains **nothing**;
  `suggestion` and `typeCodes` appear on **no** catalogue-models resource
  (ui-spec API-2, D6).
- `make generate-api`; **commit** `frontend/src/api/types.ts` (the one
  generated file a backend step may touch).
- Tests: `backend/tests/api/test_products.py` — PATCH identity happy path
  returns the recomputed slug; 409 on collision; 422 pointers on a bad year
  pair / unknown manufacturer; `suggestion` present on products and **absent
  from every catalogue-models response** (extend
  `backend/tests/api/test_catalogue_models.py`, which also asserts `variants`
  on the detail and not on the list); buildinglines route shape.

## Verification

- `make backend-test` and lint green; `make generate-api` produces a diff
  that is committed; `docker compose run --rm node-cli pnpm typecheck` green
  (the S1 additive proof).
- Live, real row (auth via the landed admin cookie + CSRF pattern): pick the
  ingested **Yamaha MT-07** row id from `/api/products`, then
  `curl -s -X PATCH localhost:8000/api/products/<id> -b cookies.txt -H "Content-Type: application/json" -H "X-CSRF-Token: $CSRF" -d '{"data":{"type":"products","attributes":{"identity":{"manufacturerId":"<yamaha-manufacturer-ulid>","buildingline":"MT","modelName":"MT-07","yearFrom":2014,"yearTo":null,"typeCodes":["RM04","RM17","RM33"],"variants":[]}}}}' | jq '.data.attributes.slug'`
  → `"yamaha/mt-07/2014-"`, and the same GET shows `queryName`,
  `typeCodes` and the `suggestion` claim block side by side.
- `curl -s localhost:8000/api/manufacturers/<yamaha-id>/buildinglines -b cookies.txt | jq` → contains `"MT"`.
- Not re-proven here: rendered-name values (6.19) and approval refusal
  (6.12/6.18); QA 6.30 owns the claim-vs-finding review behaviour.

## Risks / notes

- ui-spec API-1 marks `suggestion`'s camelCased member names *proposed* — this
  step is where they become final; record the final names in Landed decisions
  so 6.27 maps them without guessing.
- The example PATCH body above must use the Yamaha manufacturer ULID from the
  dev DB; the placeholder is deliberate — never hardcode a ULID in the step
  report without showing the query that produced it.
- 6.23 regenerates the client again (S2); keep the generator invocation
  identical (`make generate-api`).
- Append (`### Step 6.20`) to `shared-knowledge.md`: the final `identity`
  block field names, the buildinglines route path/shape, and the
  `ProductVariant`/`ProductSuggestion` wire names.
