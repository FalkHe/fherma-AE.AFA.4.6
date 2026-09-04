---
phase: 2b
step: "2b.4"
title: Phase-2b acceptance run
summary: Independent behavioural proof of the refactor — migration round-trip with seeded legacy data, get-or-create dedupe, derived products attribute, transition-matrix regression, manufacturers endpoints, and the embeddings-intact A2 guard. Tags phase-2b-done.
effort: 2
dependencies: ["2b.2", "2b.3"]
agent: qa-backend
track: qa
---

# Step 2b.4 — Phase-2b acceptance run

**Effort: 2** — independently prove the security/correctness-critical
behaviour; do **not** re-author the dev agents' infrastructure checks.

**Required reading:**
[`shared-knowledge.md`](shared-knowledge.md) — the whole contract, especially
*Invariants QA must protect* and *Landed decisions* (2b.1–2b.3 entries must
exist). The dev reports for 2b.1/2b.2/2b.3 name the landed files.
`.claude/skills/qa-checklist/SKILL.md`. Zero deviations; stop and report if one seems
necessary.

## Checks (own runs, not the dev reports)

- **Migration round-trip** with a self-seeded legacy string: from head,
  `downgrade -1` → the seeded-equivalent name is restored on `motorbikes`;
  `upgrade head` → manufacturers row + FK back. Evidence: psql output.
- **Get-or-create dedupe/race**: assigning `"suzuki "` (trailing space,
  lowercase) to a second bike creates no second row; two rapid CLI
  invocations of the same new name yield exactly one row.
- **Products API**: list + detail render the derived `manufacturer` name;
  a bike without a manufacturer renders `null`; attribute set byte-identical
  to the pinned Phase-2 contract. PATCH draftSpec/status regression — the FK
  must not disturb the transition matrix (one legal and one illegal
  transition).
- **Manufacturers API**: sorted/paginated list, detail, 404 `not-found`,
  non-admin 403; no write route exists.
- **A2 guard**: `SELECT count(*) FROM chunks WHERE embedding IS NOT NULL`
  identical to the pre-phase count; `documents` count unchanged.
- **Frontend untouched**: `make frontend-test` green; `git diff` under
  `frontend/src/` limited to the regenerated `api/schema.d.ts` (additive
  manufacturers paths only).
- Confirm `## Landed decisions` in this phase's `shared-knowledge.md` was
  appended by 2b.1/2b.2/2b.3, including the migration revision id, and that
  `../phase-3/shared-knowledge.md` + `../phase-3/step-3.1.md` now pin that
  concrete id.

## Milestone

On pass: commit, tag **`phase-2b-done`**. Phase 3 dispatching may then begin
against the updated head pointer.
