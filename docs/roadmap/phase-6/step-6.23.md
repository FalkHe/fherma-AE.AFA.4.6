---
phase: 6
step: "6.23"
title: The estimator uses the researched price
summary: _add_purchase gains the pinned precedence (used median → msrp_eur → price_band → omitted) with a mandatory assumption line naming hosts and date and "indicative" wording when stale; the additive usedPrice block lands on CostEstimatorResult and the catalogue-models detail; the client is regenerated. Opens sync point S2.
effort: 2
dependencies: ["6.22"]
---

# Step 6.23 — The estimator uses the researched price

**Effort: 2** — one precedence change in a pure service, one additive block on
two pinned shapes, a regenerated client; the snapshot machinery (6.13/6.22)
and the wire pins (D11) already exist.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D10** — the
clock lives in `used_price_service`, the snapshot with `is_stale` is an
estimator *input*, staleness is a caveat **never a refusal**; **D11** — the
exact `usedPrice` shape, additive everywhere, list resource gets nothing;
`catalogue_search_service` is **not touched** — merge-friction list). Read
`## Landed decisions ### Step 6.13/6.22` for `used_price_service`'s read API
(pinned intent: `get_snapshot(session, motorbike_id) -> UsedPriceSnapshot |
None`, `is_stale` computed from `USED_PRICE_MAX_AGE_DAYS`). Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up; a snapshot for `honda/cb500f/2013-` exists (6.22's
verification left one). **Restart `app-worker` after landing** — the
estimator runs inside the advisor's worker turn. **This step opens sync point
S2**: frontend 6.28 starts only after it is merged with the regenerated
client committed.

## Outline

- `backend/app/services/cost_estimator_service.py`:
  - `estimate` reads the snapshot once
    (`used_price_service.get_snapshot(session, motorbike_id)`) and passes it
    to `_add_purchase(parts, values, snapshot)`; no clock, no randomness —
    "reproducible given its inputs" holds because the snapshot (including
    `is_stale`) is an input.
  - `_add_purchase` precedence (D10): **used median → `msrp_eur` →
    `price_band` → omitted**. For the used case: line amount =
    `price_median_eur`; mandatory assumption line naming the source hosts
    (deduped `urlsplit(url).hostname` of `sources`, alphabetical) and the
    date — pinned wording:
    `"Purchase price is the median asking price of used listings researched on {as_of:%Y-%m-%d} from {hosts}."`
    and, appended when `sample_count` is not None,
    `" ({sample_count} prices sampled)"`. When `is_stale`, one more mandatory
    line: `"That price snapshot is from {as_of:%Y-%m-%d} and older than
    {USED_PRICE_MAX_AGE_DAYS} days — treat it as indicative."` The MSRP and
    band branches keep their existing wording verbatim. **Never refuse** on
    stale.
  - `CostEstimate` gains `used_price: UsedPriceInfo | None` (dataclass:
    `median_eur, min_eur, max_eur, sample_count, as_of, stale,
    sources: list[tuple[str, str]]` — title, url), filled from the snapshot
    whenever one exists (even when MSRP won the purchase line? No — D11 ties
    the block to the snapshot, not to the precedence: fill it whenever a
    snapshot exists; the precedence only decides the purchase *line*).
- `backend/app/llm/agents/tools/cost_estimator.py` — `CostEstimatorResult`
  gains the **additive** `used_price: UsedPriceBlock | None` (camelCased on
  the wire per D11: `{medianEur, minEur, maxEur, sampleCount, asOf, stale,
  sources: [{title, url}]}`); every landed field keeps its key and type, and
  the tool declares no `model_view` — nothing here may disturb 6.14's
  fencing arrangement.
- `backend/app/api/schemas/catalogue_models.py` + endpoint — the **detail**
  resource gains the same `usedPrice` block (one extra `get_snapshot` read on
  the detail route only); the **list** resource is untouched (no N+1, D11).
- `make generate-api`; **commit** `frontend/src/api/types.ts`.
- Tests: extend `backend/tests/services/test_cost_estimator_service.py` —
  the four-way precedence (snapshot beats MSRP beats band beats omitted),
  the pinned assumption wordings, the stale line via an injected snapshot
  with `is_stale=True` (staleness itself is `used_price_service`'s tested
  clock — do not re-test the threshold here), block filled while MSRP wins
  the line; extend the tool test (keys additive) and
  `backend/tests/api/test_catalogue_models.py` (detail carries `usedPrice`,
  list does not).

## Verification

- `make backend-test` and lint green; `make generate-api` diff committed;
  `docker compose run --rm node-cli pnpm typecheck` green (the S2 additive
  proof); `docker compose restart app-worker`.
- Live, real row:
  `app tools run cost_estimator '{"motorbikeName":"Honda CB500F"}'` — the
  purchase line equals the snapshot's median, `usedPrice` is filled, and an
  assumption names the hosts and the date. Then
  `curl -s localhost:8000/api/catalogue-models/<cb500f-id> -b cookies.txt | jq '.data.attributes.usedPrice'`
  shows the same block, and the list route's cards carry no `usedPrice` key.
- Not re-proven here: research/robots behaviour (6.22) and the chat-surface
  rendering (frontend 6.28 / QA 6.31, including the M4 "indicative" demo).

## Risks / notes

- `git diff backend/app/services/catalogue_search_service.py` must be empty
  — that file belongs to 6.19 alone this phase.
- The three Phase-4 OQ2 guessed MSRPs remain in `msrp_eur`; after this step
  a researched median simply outranks them — do not delete or "fix" those
  values here (6.29 documents the situation).
- If `used_price_service.get_snapshot`/`UsedPriceSnapshot` landed under
  other names in 6.13, use the landed names; a missing `is_stale` on the
  read model is a stop-and-report (D10 puts the clock there, not here).
- Append (`### Step 6.23`) to `shared-knowledge.md`: the pinned assumption
  wordings (6.28's UI copy and QA 6.31 quote them) and confirmation that
  every pre-step `CostEstimatorResult` key survived unchanged.
