---
phase: 2
step: "2.21"
title: Phase-2 acceptance run
summary: Execute the phase done-criterion end-to-end in a real browser and file pass/fail evidence — admin adds "Suzuki GSR 600", watches live progress, reviews documents/specs/image, corrects a value, approves; the model is live with verified specs and embedded chunks.
effort: 1
dependencies: ["2.19", "2.20"]
agent: qa-frontend
track: qa
---

# Step 2.21 — Phase-2 acceptance run

**Effort: 1** — verification only; no implementation. QA owns behavioural
coverage and independently confirms the security/correctness-critical
behaviour instead of trusting dev reports.

**Required reading:** [`shared-knowledge.md`](shared-knowledge.md) (the
contract being proven), [`ui-spec.md`](ui-spec.md) (expected states),
`docs/roadmap.md` Phase-2 done-criterion.

## Acceptance script (verbatim, in order)

1. Stack up (`make up`, worker included), fresh admin login.
2. `/admin`: add **"Suzuki GSR 600"** via the dialog.
3. Watch the row **live, without reloading**: progress bar + pinned status
   messages advance; chip flips `ingesting → in_review` when done.
4. Open review: ≥3 documents with titles/URLs/types, Wikipedia first,
   Markdown rendered (GFM table visible, raw HTML inert).
5. Specs tab: draft has plausible engineCc/powerKw/seatHeightMm; **correct
   one value**, save (snackbar).
6. Image tab: variants + attribution visible.
7. Approve (confirm dialog) → chip `approved`, action bar gone; backlog row
   shows `approved`.
8. API/DB evidence: `GET /api/products?filter[status]=approved` shows the
   model with `verifiedSpec` **matching the edit**; psql: chunks for the
   bike have non-null embeddings + model string; image rows `approved`.
9. Security spot-checks (independent, not from dev reports): review routes
   as non-admin user → redirected; products write without CSRF header →
   403; `GET /api/events` without cookie → 401.
10. Failure path: force an ingestion failure (e.g. bogus model name that
    yields zero documents) → operation `failed` with error on the row,
    status back to `backlog`, retry re-enqueues.

## Deliverable

Pass/fail report with screenshots as evidence per step, filed to the
coordinator. Any deviation from the pinned contract is a finding — do not
fix, report.
