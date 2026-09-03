---
phase: 6
step: "6.18"
title: Identity backfill CLI and the approval CHECK constraint
summary: app catalogue backfill-identity (deterministic, never re-ingestion) strips the FK'd manufacturer prefix into model_name, recomputes slugs and prints the rows still missing a year range; then the fourth and final migration adds the approved-implies-identity CHECK, NOT VALID then VALIDATEd.
effort: 3
dependencies: ["6.12", "6.13"]
---

# Step 6.18 — Identity backfill CLI and the approval CHECK constraint

**Effort: 3** — one deterministic CLI command, a small data preparation on the
dev DB, and the phase's fourth (final) migration with its round trip.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**D4** including
its stated ordering exception; hard rules — exactly four migrations, this is
the fourth; re-ingestion is never a data-migration tool, the 2b rule). Detail:
`docs/roadmap/model-naming-data-model.md` §3 (slug policy), §7 rows N6/N7 (the
backfill's honest limits). Read `## Landed decisions ### Step 6.12` for the
exact `assign_identity` signature and the `app catalogue set-identity`
invocation, and `### Step 6.13` for the current migration head. Agent:
**backend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** stack up. Alembic head must be **6.13's migration id** before
this step creates its migration — anything else is a stop-and-report (no
branching heads, no merges). No `app-worker` restart needed (CLI + migration
only), but the migration must be applied inside the container.

## Outline

- `backend/app/cli/catalogue.py` — new command
  `app catalogue backfill-identity [--dry-run]`. **Deterministic, never
  re-ingestion** (a fresh run would delete documents and embeddings — the 2b
  rule). For every motorbike whose `model_name IS NULL` **and**
  `manufacturer_id IS NOT NULL`:
  - derive `model_name` = `query_name` minus the FK'd manufacturer's `name`
    as a case-insensitive prefix (`"BMW S 1000 XR"` − `"BMW"` →
    `"S 1000 XR"`); a `query_name` that does not start with the
    manufacturer's name keeps `query_name` verbatim as `model_name`;
  - write through `product_service.assign_identity` (D2 — the only writer),
    passing the row's existing `buildingline`, `year_from`, `year_to`,
    `type_codes` and `variants` unchanged; the slug recompute is
    `assign_identity`'s job (canonical slash shape only once the identity is
    complete, D3). **Never** copy anything from `suggestion` (D6);
  - a `DuplicateModelError` on the recompute: print the collision, leave the
    row unchanged, continue (never delete a motorbike row);
  - rows with no `manufacturer_id` are listed as skipped.
  Then print the pinned gap table: **every row still missing a year range**
  (`year_from IS NULL`), flagging approved ones. `--dry-run` prints what
  would be set and writes nothing. Follows the `app.cli.users` async pattern.
- **Data preparation (live dev DB, before the migration):** the currently
  approved rows must satisfy the constraint. Check with
  `docker compose exec postgres psql -U postgres -d app -c "select query_name, model_name, year_from from motorbikes where status = 'approved';"`.
  Expected: the three seeded models. Fill their year ranges via 6.12's CLI
  (admin-entered public production years, deterministic — not an LLM guess):
  `app catalogue set-identity bmw-s-1000-xr --manufacturer "BMW" --model-name "S 1000 XR" --year-from 2015`,
  `app catalogue set-identity honda-cb500f --manufacturer "Honda" --model-name "CB500F" --year-from 2013`,
  `app catalogue set-identity suzuki-gsr600 --manufacturer "Suzuki" --model-name "GSR600" --year-from 2006 --year-to 2011`
  (confirm the exact slugs with the `psql` query above first — they are the
  seeded provisional ones until this very command recomputes them). Any
  *other* approved row missing an identity is a stop-and-report.
- **Migration** (created after the backfill ran clean):
  `backend/alembic/versions/…_approved_identity_check.py`,
  `down_revision` = 6.13's id. Upgrade, in this order in one migration:
  `ALTER TABLE motorbikes ADD CONSTRAINT ck_motorbikes_approved_identity_complete CHECK (status <> 'approved' OR (manufacturer_id IS NOT NULL AND model_name IS NOT NULL AND year_from IS NOT NULL)) NOT VALID;`
  then
  `ALTER TABLE motorbikes VALIDATE CONSTRAINT ck_motorbikes_approved_identity_complete;`
  (D4: a violating row fails the upgrade loudly). Downgrade drops the
  constraint. No fifth schema change of any kind.
- Tests: `backend/tests/cli/test_catalogue.py` — prefix stripping, verbatim
  fallback, suggestion untouched, dry-run writes nothing, collision reported
  and skipped, gap table printed.

## Verification

- `make backend-test` and lint green.
- `app catalogue backfill-identity --dry-run` on the dev DB lists every FK'd
  row and what it would set; the live run then shows populated `model_name`
  and, for the three approved rows after `set-identity`, canonical slugs:
  `docker compose exec postgres psql -U postgres -d app -c "select slug from motorbikes where status = 'approved';"`
  → `bmw/s-1000-xr/2015-`, `honda/cb500f/2013-`, `suzuki/gsr600/2006-2011`.
- Migration round trip inside the container, output pasted into the report:
  `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head`.
- The constraint bites:
  `docker compose exec postgres psql -U postgres -d app -c "update motorbikes set model_name = null where status = 'approved';"`
  fails with `ck_motorbikes_approved_identity_complete` (nothing committed).

## Risks / notes

- The stated D4 ordering exception applies: this model change sits after the
  backfill on purpose — do not "move it to M1".
- The dev DB may hold near-duplicate rows (seeded `Suzuki GSR600` vs. the
  imported `Suzuki GSR 600 (2006–2011) [WVB9]` — different provisional
  slugs). The backfill must survive that: distinct `model_name` spellings
  produce distinct slugs, and any real collision follows the report-and-skip
  rule above. List what you saw in the report.
- 6.19 depends on the canonical slugs this step produces (`resolve_name`'s
  exact-slug leg) and on the gap table being honest — do not fill year
  ranges for backlog rows.
- Append (`### Step 6.18`) to `shared-knowledge.md`: the migration id (the
  phase's final head), the constraint name, and the three approved rows'
  canonical slugs.
