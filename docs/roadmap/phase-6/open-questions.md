# Phase 6 — Open questions

Anything a step cannot decide on its own. **Nothing here blocks the dispatch of
6.9–6.31**: every item below either has a working default recorded in
[`shared-knowledge.md`](shared-knowledge.md) or is explicitly out of scope.

---

## Resolved at slicing time (2026-08-31) — recorded for the audit trail

- **Used-price source strategy (roadmap 6.4's robots/ToS gate).** Closed by
  **D8**: no purpose-built classifieds scraper. `robots.txt` for
  kleinanzeigen.de and mobile.de was fetched on 2026-08-31 and disallows
  precisely the price-filter, sort and search-parameter paths a sampler would
  use, so the phase reuses the landed search→fetch→extract pipeline over
  search-provider-returned URLs only, adds a stdlib `urllib.robotparser` gate
  on the price path, and documents that the result is a *published-price
  snapshot*, not a classifieds sample. The evidence and the exact disallow
  lines are in D8 so nobody re-opens this.
- **Where used prices live.** Closed by **D9**: a new
  `motorbike_used_prices` table, outside the draft/verified split;
  `msrp_eur`/`price_band` untouched.
- **Storage of trims and type codes, buildingline, aliases, slug shape.**
  Closed by the owner on 2026-08-31 —
  [`../model-naming-data-model.md`](../model-naming-data-model.md) §0 (D1–D6),
  restated as **D1** here.
- **`products.name` — rendered name or `queryName`?** Closed by data-model
  OQ-7 and **D10**: `name` keeps its key and becomes the rendered name;
  `queryName` is added alongside. The SPA compiles unchanged.
- **Theme 6.8's premise.** Refuted at slicing time — `heading_path` is already
  capped at 512 in `chunking.py` and in the column. Re-scoped into 6.14 as a
  payload-side cap plus an audit; **no fifth migration**. See the Theme
  mapping note.
- **N1–N9 vs. 6.1–6.8 double-slicing.** Resolved: the `N` numbers are
  superseded by 6.9–6.31 and the overlapping slices are merged, not run twice.

## Standing recommendations (hold unless the owner says otherwise)

- **OQ-6 (carried from the data-model doc) — year ranges for the 12 seeded
  models.** 6.18's backfill derives `model_name` mechanically and **prints the
  rows still missing a year range**; an admin fills those through the review
  form. Not LLM-guessed: an invented year range would be an unverified number
  inside a customer-visible name. The `approved ⇒ identity complete` CHECK
  (D4) is what forces the gap closed, and 6.30's acceptance is where the list
  has to be empty for the demo corpus.
- **OQ-10 — ambiguous customer input ("BMW GS").** Prompt handling on a
  multi-candidate resolver result, not a ninth tool.
- **Used-price cadence.** Nothing schedules `app prices research`. Re-running
  it is a manual admin action, and the staleness caveat (D10) is what keeps an
  old snapshot honest in the meantime. A cron/Taskiq schedule is a later
  change if the owner wants one.

## Carried over (tracked elsewhere, listed for visibility)

- **Phase-5 OQ — `a2Eligible` is not cross-checked against power.** Still the
  owner's call (derived-consistency validator vs. deriving the flag from power
  at query time). Explicitly **out of Phase-6 scope** by **D15**: it is
  unrelated to this phase's three themes and would inject an unrequested
  behaviour change into the extraction path that 6.15/6.17 already rewrite.
  Stays open in [`../phase-5/open-questions.md`](../phase-5/open-questions.md).
- **Q4 / Phase-4 OQ4 — concurrent-turn 409 race.** Owner decision still
  pending; the fix changes a Phase-3 pin. Out of scope by **D15**, still a
  documented known limitation.
- **Phase-4 OQ2 — guessed demo prices.** This phase is the fix for the three
  original models, but only once 6.22 has actually researched them. Until then
  6.29 keeps the "not verified market data" wording.
- **Future upgrades** (trim-aware filtering, buildingline as a table, per-trim
  type codes, per-trim provenance, `model_years`) — recorded in
  [`../../roadmap.md`](../../roadmap.md); none of them is in this phase.

## Open — needs the owner only if it actually bites

- **Manufacturer merge blast radius (6.16).** Merging `Kawasaki Motors` into
  `Kawasaki` re-points the affected rows' `manufacturer_id`, which changes
  their **slug** (D3) once they have an identity. That is intended and safe
  (nothing stores a slug), but if the merge is run on rows that are already
  approved *and* already identified, the recompute can in principle collide
  with an existing slug. 6.16's default: report the collision and leave both
  rows untouched for an admin to merge deliberately — never auto-delete a
  motorbike row. Escalate only if the dev DB actually produces a collision.
