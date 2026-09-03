---
phase: 4
step: "4.11"
title: Phase-4 acceptance run
summary: The phase done-criterion end-to-end with evidence — a fresh user filters the catalogue, opens a model detail from a recommendation card, an unapproved model is unreachable by direct URL — plus the 409-race re-proof; then tag phase-4-done.
effort: 2
dependencies: ["4.5", "4.9", "4.10"]
---

# Step 4.11 — Phase-4 acceptance run

**Effort: 2** — an execution-and-evidence step across both tracks.

Binding contracts: `docs/roadmap/phase-4/shared-knowledge.md` and
`docs/roadmap/phase-4/ui-spec.md` (§11 verification hooks). Agents:
**qa-frontend** leads (browser walk with screenshots), **qa-backend**
re-runs the curl matrix and the race proof independently of the dev
reports. QA owns behavioural coverage — do not merely re-run the dev
agents' infrastructure checks.

## Outline

- **Fresh-user browser walk (screenshots as evidence):** register a new
  account → Catalogue nav entry → grid renders approved models → set 3+
  filters incl. a range and a multi-select → reload → identical view →
  copy the URL into a second session → login redirect lands on the same
  filtered view → open a detail page: grouped verified specs, article
  prose, always-expanded Sources block with working external links, image
  attribution (or the pinned fallbacks) → from a consultation, click a
  recommendation card → the matching detail page.
- **Role-scoping curl matrix (independent):** plain user 200 on
  `/api/catalogue-models` (approved only — cross-check against the DB
  statuses), 403 on `/api/products`, 200 on `/api/manufacturers`; an
  `in_review`/`backlog`/`rejected` id → 404 on the detail endpoint **and**
  the 404 UI state by direct URL; every filter family narrows; both sorts
  order correctly with NULLS LAST on price.
- **Mobile pass:** 360 px viewport — filter drawer fully operable, no
  horizontal page scroll on either screen (ui-spec §10).
- **Q4 re-proof (if 4.5 landed):** two truly parallel message POSTs →
  exactly one 201 + one 409, exactly one operation row.
- **Regression spot-check:** admin backlog/review screens unaffected
  (i18n hoist!), a Phase-3 consultation still renders tool results and
  cards.
- Record findings; non-blocking polish goes to `open-questions.md` /
  Phase 5; tag **`phase-4-done`**.

## Verification

- The roadmap Phase-4 done-criterion holds end-to-end with recorded
  evidence: a fresh user filters the catalogue, opens a model detail page
  from a recommendation card, and an unapproved model is unreachable by
  direct URL.

## Risks / notes

- If no approved model carries a verified price yet (open-questions OQ2),
  record the price-sort/band checks as executed-with-nulls and flag the
  demo gap — not a failure.
