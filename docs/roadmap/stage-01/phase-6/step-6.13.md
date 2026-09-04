---
phase: 6
step: "6.13"
title: Used-price storage and the staleness service
summary: Third migration creates motorbike_used_prices exactly as pinned in D9 and adds the `listing` source_type enum value; used_price_service owns snapshot reads/writes and the staleness clock; USED_PRICE_MAX_AGE_DAYS lands in config.py and .env.dist together. No reader, no scraping, no CLI.
effort: 3
dependencies: ["6.10"]
---

# Step 6.13 — Used-price storage and the staleness service

**Effort: 3** — one new table + enum value with a documented asymmetric
downgrade, one small service with the staleness contract, the phase's single
config key, tests; nothing reads it yet.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (**D9** — the
exact column table, full-object replace, no kind split, "a run that cannot
produce a median writes nothing"; **D10** — the service owns the clock;
hard rules — migration 3 of 4, and the **only** new config key of the phase).
Agent: **backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up for the psql checks. This step is independent of
6.11/6.12 (may run in parallel per the within-track rule) **but its migration
must be created after 6.10's** — `down_revision` = 6.10's revision id; a
different head is a stop-and-report.

## Outline

- New migration, `down_revision` = 6.10's revision (see its landed-decisions
  entry):
  - `op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'listing'")`
    **first** (PostgreSQL can add but never drop an enum value);
  - `op.create_table("motorbike_used_prices", …)` with **exactly** the D9
    columns: ULID `id` PK (String(26)); `motorbike_id`
    `ForeignKey("motorbikes.id", ondelete="CASCADE")` with a **UNIQUE**
    constraint; `price_min_eur`/`price_max_eur`/`price_median_eur`
    `Integer NOT NULL`; `sample_count` `SmallInteger NULL`; `as_of`
    `DateTime(timezone=True) NOT NULL`; `sources` JSONB
    `NOT NULL server_default '[]'::jsonb`; `created_at`/`updated_at` as on
    `motorbikes`;
  - downgrade drops the table only, with a module-docstring paragraph stating
    that the `listing` enum value **remains** (undroppable) and why that is
    harmless (no row can reference it once 6.21's writers are gone).
- `backend/app/db/models/source_document.py`: `SourceType.LISTING = "listing"`
  with a comment (quarantined from RAG and from re-ingestion deletes — D12,
  enforced in 6.21).
- **New** `backend/app/db/models/motorbike_used_price.py`: `MotorbikeUsedPrice`
  (`ULIDPrimaryKeyMixin, Base`), docstring documenting the pinned snake_case
  `sources` entry shape
  `[{"source_document_id", "url", "title", "sample_count", "prices": [int, …]}]`
  and "NULL `sample_count` = unknown, never zero" (D8/D9). Register it in
  `backend/app/db/models/__init__.py`.
- **New** `backend/app/services/used_price_service.py` (owns its transactions):
  - `@dataclass(frozen=True, slots=True) class UsedPriceSnapshot`:
    `motorbike_id`, `price_min_eur`, `price_max_eur`, `price_median_eur`,
    `sample_count`, `as_of`, `sources`, `is_stale`;
  - `async def get_snapshot(session, motorbike_id: str) -> UsedPriceSnapshot | None` —
    computes `is_stale = (datetime.now(UTC) - as_of) > timedelta(days=settings.used_price_max_age_days)`
    at read time (D10: the clock lives here, the snapshot is the estimator's
    input);
  - `async def upsert_snapshot(session, motorbike_id: str, *, price_min_eur: int, price_max_eur: int, price_median_eur: int, sample_count: int | None, as_of: datetime, sources: list[dict[str, Any]]) -> MotorbikeUsedPrice` —
    full-object replace of the one row per bike (D9), commits, announces
    `product.updated` via `operation_service.notify` (the catalogue detail
    will render the snapshot — same after-commit ordering rule as
    `product_service._announce`);
  - `async def delete_snapshot(session, motorbike_id: str) -> bool` — commits,
    announces when a row was deleted; `False` when none existed;
  - `def is_stale(as_of: datetime, *, now: datetime | None = None) -> bool` —
    the one comparison, exported for tests.
- `backend/app/core/config.py`: `used_price_max_age_days: int = 180`, comment
  pointing at D10; `.env.dist`: `USED_PRICE_MAX_AGE_DAYS=180` with a matching
  comment — **both in this step, together** (hard rule).
- Tests: **new** `backend/tests/services/test_used_price_service.py` (stubbed
  session per `tests/conftest.py` conventions): upsert insert-vs-replace,
  delete both paths, announce ordering, and `is_stale` boundaries — exactly
  180 days old is **not** stale (strict `>`), 181 days is; `sample_count=None`
  round-trips as None.

## Verification

- Migration round trip in the container, output pasted — note the expected
  asymmetry: after `downgrade -1`,
  `docker compose exec postgres psql -U app -d application -c "SELECT enum_range(NULL::source_type)"`
  still lists `listing` (documented, not a failure); after `upgrade head`,
  `… -c '\d motorbike_used_prices'` shows the FK-with-UNIQUE, the NOT NULLs
  and the `sources` default.
- `make backend-test` + `make lint` green.
- Config wiring: `docker compose run --rm app-cli python -c "from app.core.config import get_settings; print(get_settings().used_price_max_age_days)"`
  prints `180`.

## Risks / notes

- **No reader, no writer beyond the service, no CLI, no scraping** — 6.21/6.22
  write snapshots, 6.23 wires the estimator/API reader (D10's purchase-price
  precedence lands there, not here). `price_band`/`msrp_eur` stay untouched
  new-bike fields (D9).
- `ALTER TYPE … ADD VALUE` runs inside Alembic's transaction — legal on
  PG ≥ 12 (we run pg16) as long as this migration does not also *use* the
  value; it does not.
- 6.21–6.23 and frontend 6.28 depend on the D9 `sources` shape and the
  snapshot field names; frozen once landed.
- Append (`### Step 6.13`) to `shared-knowledge.md`: the migration revision id
  (6.18 chains on it), the service's public names, and the strict-`>`
  staleness boundary.
