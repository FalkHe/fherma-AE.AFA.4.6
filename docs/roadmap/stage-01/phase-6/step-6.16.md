---
phase: 6
step: "6.16"
title: Manufacturer-name normalisation against the known marques
summary: A generated, committed known-marques constant module derived from bike-list.txt; manufacturer_service.normalize_name maps case-insensitive prefix matches onto the canonical marque; the existing Kawasaki / Kawasaki Motors split is merged through the per-model CLI. Closes the Phase-5 open question.
effort: 3
dependencies: []
---

# Step 6.16 — Manufacturer-name normalisation against the known marques

**Effort: 3** — one constant module, one function change with real blast
radius (every `normalize_name` caller inherits it), a data merge on the live
dev DB, and tests.

Binding contract: `docs/roadmap/stage-01/phase-6/shared-knowledge.md` (**D14** — the
whole design is pinned there) and `open-questions.md` (last item — the merge
collision policy). Agent: **backend-dev**. Zero deviations — a deviation is a
stop-and-report.

**Environment:** stack up (`make up`) for the merge and the live check; no
migration in this step. **Restart `app-worker` after landing** — extraction
calls `normalize_name` inside the worker. This step has no dependency on
6.9–6.15 and may be pulled forward (shared-knowledge, within-track
independence).

## Outline

- **New** `backend/app/services/known_marques.py` — a *generated, committed*
  constant module (D14: never a runtime parse of the resource file):

  ```python
  KNOWN_MARQUES: tuple[str, ...] = (
      "Aprilia", "BMW", "Ducati", "Harley-Davidson", "Honda",
      "Kawasaki", "KTM", "Suzuki", "Triumph", "Yamaha",
  )
  ```

  The module docstring records the derivation (the distinct first
  whitespace-separated token of every entry line in
  `backend/resources/bike-list.txt`, canonical casing as printed there) and
  the regeneration rule: re-derive and re-commit when the resource file gains
  a marque. Verify the tuple against the file before committing:
  `awk '{print $1}' backend/resources/bike-list.txt | grep -v '^\[' | sort -u`.
- `backend/app/services/manufacturer_service.py` — extend `normalize_name`:
  after the existing trim/collapse/truncate, match the collapsed name
  case-insensitively against `KNOWN_MARQUES`, **longest marque first**: an
  exact match or a match of `"{marque} "` as a prefix returns the marque's
  canonical spelling (`"Kawasaki Motors"` → `"Kawasaki"`, `"Honda Motor"` →
  `"Honda"`, `"bmw"` → `"BMW"`). Anything else passes through unchanged —
  never invent a marque. Docstring updated; every caller (`get_or_create`,
  extraction's `_assign_identity`/`_assign_manufacturer`, `app catalogue
  set-manufacturer`) inherits the mapping by construction, which is the point.
- **Data merge, live dev DB, per-model CLI path (never a row delete):**
  1. list the split:
     `docker compose exec postgres psql -U postgres -d app -c "select mb.slug, m.name from motorbikes mb join manufacturers m on m.id = mb.manufacturer_id where m.name <> 'Kawasaki' and m.name ilike 'kawasaki%';"`
     — expected corpus per D14: the Versys 650 row on `Kawasaki Motors`
     (Z400/Z900 already on `Kawasaki`).
  2. for each listed slug: `app catalogue set-manufacturer <slug> Kawasaki`.
  3. the now-unreferenced `Kawasaki Motors` manufacturers row is **left in
     place** (no admin CRUD for manufacturers, D15; it is inert). If a
     re-point would ever collide two motorbike slugs, report and leave both
     rows untouched — never auto-delete a motorbike row (open-questions, last
     item). With pre-identity slugs (`slugify(query_name)`) no collision is
     expected here.
- Tests — extend `backend/tests/services/test_manufacturer_service.py`:
  prefix mapping (`"Kawasaki Motors"` → `"Kawasaki"`, `"KTM
  Sportmotorcycle"` → `"KTM"`), case-insensitive (`"kawasaki motors"` →
  `"Kawasaki"`, `"bmw"` → `"BMW"`), exact marque, unknown marque passes
  through verbatim (`"MV Agusta"`), mid-string containment never matches
  (`"Big Honda Fan Club"` passes through unchanged — the marque must be the
  first word), and `None`/whitespace behaviour unchanged.

## Verification

- `make backend-test` and lint green; `docker compose restart app-worker`.
- Live: after the merge,
  `docker compose exec postgres psql -U postgres -d app -c "select m.name, count(*) from motorbikes mb join manufacturers m on m.id = mb.manufacturer_id where m.name ilike 'kawasaki%' group by m.name;"`
  shows every row on `Kawasaki` and none on `Kawasaki Motors`.
- One CLI probe of the new mapping without touching data:
  `app catalogue set-manufacturer kawasaki-versys-650 "Kawasaki Motors"`
  re-points to the existing `Kawasaki` row (idempotent — the command prints
  the `Kawasaki` manufacturer id, and `select count(*) from manufacturers
  where name ilike 'kawasaki%'` does **not** grow).

## Risks / notes

- `normalize_name` is also the display-name normaliser inside
  `get_or_create`; after this step `get_or_create("Kawasaki Motors")` returns
  the `Kawasaki` row. That is D14's intent — state it in the docstring so
  nobody "fixes" it.
- This closes the Phase-5 open question "manufacturer names are
  inconsistent": append the closure (date + this step number) to
  `docs/roadmap/stage-01/phase-5/open-questions.md`.
- 6.18's backfill strips the FK'd manufacturer's name as a prefix of
  `query_name` — it relies on the canonical spellings this step establishes.
- Append (`### Step 6.16`) to `shared-knowledge.md`: the module path of
  `KNOWN_MARQUES` and the merged state of the dev DB.
