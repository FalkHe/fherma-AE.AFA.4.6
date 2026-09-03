---
phase: 6
step: "6.30"
title: "M3 acceptance: researched identity end-to-end"
summary: QA gate for milestone M3 — a real backlog claim ingested end-to-end, claim beside finding, approval refused while incomplete, path-shaped slug, year ranges only on collision, no type code on any customer surface, the marque merge, and an empty backfill missing-year list; behavioural and independent of the dev reports.
effort: 3
dependencies: ["6.27"]
---

# Step 6.30 — M3 acceptance: researched identity end-to-end (QA)

**Effort: 3** — one end-to-end ingestion plus a curl/DOM matrix and
screenshot evidence; behaviour only, no infrastructure re-checks.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**the M3 row
of the milestone table is the checklist** — quote it and answer item by
item; D2–D6, D13, D14 are the contracts to prove or refute) and
`docs/roadmap/phase-6/ui-spec.md` §1, §2, §5 (the identity rows of the
screen×state matrix). Read the **Landed decisions** entries of 6.15–6.20
and 6.24–6.27 for the exact CLI names, labels and test ids the devs
pinned. Agent: **qa** (qa-backend + qa-frontend; browser evidence via
Playwright). Zero deviations — a deviation is reported, not worked around.

**Environment:** stack up (`make up`), `app-worker` restarted after
6.14–6.19; the imported 200-row backlog present; a scratch admin account.
**Never `docker compose down`** — use `stop` if needed.

## Outline

All checks are **independent re-derivations — do not trust the dev
reports**, and do **not** re-author their infrastructure checks (migration
round trips, lint, unit suites — QA owns behaviour):

- **End-to-end research on a real claim:** pick the M3 corpus row from
  `backend/resources/bike-list.txt` — `BMW R 1200 GS (2004–2018)
  [K25/K50]`, a claim carrying type codes worth contradicting. Start
  ingestion from the admin backlog; verify the run consumed
  `suggestion.links` and searched the type codes (worker logs /
  operation), and filled `manufacturer`, `modelName`, `yearFrom`/`yearTo`,
  `typeCodes` and any `variants` the sources printed.
- **Claim beside finding (D6/§2):** the identity tab shows the claim panel
  and per-field claim rows next to the researched values; "use the claim"
  fills the form buffer only (dirty, not saved); a contradicted claim
  surfaces as the §2.4 warning Alert, and neither claim nor finding was
  silently overwritten (D13).
- **Approval gate (D4/§1.6):** with an incomplete identity, approve → 422
  `incomplete-identity` and the specific dialog message; after completing
  and saving, approval succeeds.
- **Slug (D3):** the approved row's slug is exactly
  `bmw/r-1200-gs/2004-2018` (curl the admin products resource).
- **Year ranges only on collision (D5):** across the R 1200/1250/1300 GS
  group, catalogue and tool surfaces show the year range; a model with no
  same-name sibling renders **without** one (curl `catalogue-models` +
  screenshots).
- **Type codes never on a customer surface (D6):** curl the
  `catalogue-models` list and detail — no `typeCodes`, no `suggestion`
  member anywhere in the payload; DOM of the catalogue pages carries no
  code string.
- **Marque merge (D14):** `Kawasaki` and `Kawasaki Motors` are one
  manufacturer in `/api/manufacturers` and the catalogue filter; the
  Versys 650 row sits under `Kawasaki`.
- **Backfill:** the identity backfill CLI's (exact name per 6.18's Landed
  decisions) "missing year range" list is **empty** for the demo corpus.
- Evidence: screenshots for every UI claim, curl transcripts for every
  wire claim; clean up scratch data.
- On pass, the coordinator tags `phase-6-m3`.

## Verification

- The M3 demo criterion is quoted and answered item by item; every failure
  is filed with reproduction steps. This step is the **only** place the M3
  criterion is formally proven.

## Risks / notes

- Research output is nondeterministic — if the run fills less than the M3
  row expects, report what it found verbatim; the criterion's spirit is
  the pipeline, corrections through the review form are legitimate (an
  admin correcting a wrong year is part of the story, not a failure).
- The `approved ⇒ identity complete` CHECK (6.18) makes the approval gate
  double-enforced — probe the API, not the DB constraint (infra is the
  dev's proof).
- Fencing and prices are out of scope here — 6.31 owns them; do not
  duplicate.
