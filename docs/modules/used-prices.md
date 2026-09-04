# Used prices

> **Status: storage and UI only.** Nothing writes or reads a used price in any
> user-facing path. There is no research command, the cost estimator does not
> consult the table, and no API payload carries a `usedPrice` field. The
> frontend components exist and are dormant. Read this before assuming the
> feature works.

## Why it exists at all

`msrp_eur` and `price_band` are **new-bike** figures. Someone shopping for a
used motorcycle needs what the machine actually sells for today, which is a
different number with a different shelf life — hence a separate table rather
than a third spec revision.

## What is built

**`motorbike_used_prices`** — one row per motorbike (`motorbike_id` FK CASCADE,
UNIQUE):

| Column | Note |
|---|---|
| `price_min_eur`, `price_max_eur`, `price_median_eur` | Integer, NOT NULL |
| `sample_count` | `SmallInteger` nullable — NULL means *unknown*, not zero |
| `as_of` | timestamptz; the snapshot date is part of the claim |
| `sources` | JSONB `[{source_document_id, url, title, sample_count, prices}]` |

Deliberately outside the draft/verified split: a price is not a specification an
admin verifies once, it is a dated observation that expires.

**`used_price_service`** — `get_snapshot`, `upsert_snapshot`, `delete_snapshot`,
`is_stale`, and the frozen `UsedPriceSnapshot`. Staleness is a strict
`>` comparison against `USED_PRICE_MAX_AGE_DAYS` (default 180). Included in
`app snapshot` so demo data round-trips.

**`SourceType.LISTING`** and its quarantine. Price provenance is stored as a
source document, but a dated asking price must never become timeless
retrievable prose or move a spec. `listing` documents are therefore excluded
from the re-ingestion discard (they survive a fresh run), from embeddings, from
the extraction prompt, and from customer-visible sources. They *are* shown on
admin document surfaces.

**`ingestion/robots.py::RobotsGate`** — stdlib `urllib.robotparser`, per-host
cache; 2xx parses, 401/403 disallow, other 4xx allow, 5xx or timeout disallow.
Implemented and tested, **wired into nothing.**

**Frontend** — `UsedPriceSnapshot.tsx` plus the `usedPrice.ts` type guard
(`{medianEur, minEur, maxEur, sampleCount, asOf, stale, sources[{title, url}]}`),
consumed by the catalogue detail page and by the cost-estimator tool block, both
only when a valid `usedPrice` validates. It never does today. `i18n`
`common.usedPrice.*` keys are in place.

## What is not built

- **No `app prices research` / `app prices delete`** — no `prices` CLI sub-app,
  no research service, no extraction prompt for prices.
- **The `RobotsGate` is not called** by any fetch path.
- **The cost estimator does not consult the table.** It still prices from
  verified `msrp_eur`, falling back to the price-band midpoint. (A comment on
  `used_price_max_age_days` in `config.py` describes estimator behaviour that
  does not exist.)
- **No `usedPrice` on any payload** — not on the cost-estimator tool result, not
  on catalogue detail, and not in the generated `schema.d.ts`. The frontend
  types it locally as a stand-in.
- **No admin editing** of used prices anywhere.
- **No refresh cadence.** Nothing schedules research; it was always meant to be
  a manual admin action, with the staleness caveat keeping an old snapshot
  honest.

## The source constraint

This is the decision that shaped the whole design and should not be
re-litigated. `robots.txt` for the obvious German classifieds sites
(kleinanzeigen.de, mobile.de) **disallows precisely the price-filter, sort and
search-parameter paths** a price sampler would need. So:

- no purpose-built classifieds scraper;
- research would reuse the landed search → fetch → extract pipeline over URLs a
  search provider itself returned, behind the robots gate;
- the result must be described for what it is — **a dated snapshot of published
  used prices with visible sources, not a statistical sample of a classifieds
  database**;
- staleness is a *caveat*, never a refusal: an old snapshot is shown with its
  date and the word "indicative".

## If this gets finished

The remaining work is the research writer (`upsert_snapshot`'s only caller), the
robots gate wiring, an additive `usedPrice` member on the cost-estimator result
and the catalogue detail payload, `make generate-api`, and deleting the
frontend's local stand-in type. One further carve-out is still open:
`chunking.rebuild_for_motorbike` does not exclude `listing` documents, so a
manual re-chunk would embed price prose.
