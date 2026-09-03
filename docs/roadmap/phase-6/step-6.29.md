---
phase: 6
step: "6.29"
title: "Docs: identity, prices, the CLI reference and the grading map"
summary: Documentation catch-up against landed behaviour — ingestion.md gains the identity fields, the claim-not-data rule and the listing quarantine; README gains the five new CLI commands and the one new config key; demo-walkthrough gains an identity+price chapter; core-requirements-checklist and model-naming cross-links updated — with three explicit honesty requirements.
effort: 3
dependencies: ["6.23"]
---

# Step 6.29 — Docs: identity, prices, the CLI reference and the grading map

**Effort: 3** — five documents, every documented command replayed verbatim
before it is written down, and three honesty rules that require checking
the live DB state, not just prose.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (D6, D7, D8,
D9, D10, D14 and the **Landed decisions** entries of 6.15–6.23 for exact
command names, flags and output). Agent: **docs-writer**. Zero deviations —
a deviation is a stop-and-report.

**Environment:** stack up (`make up`) to replay every documented command;
the imported backlog and at least one researched price snapshot present.

## Outline

- `docs/ingestion.md`:
  - the identity fields research now fills (`manufacturer`, `modelName`,
    `yearFrom`/`yearTo`, `typeCodes`, `variants`) and that
    `assign_identity` is the single writer (D2);
  - **`suggestion` is a claim, not data** (D6): an input hint and a
    reviewer comparison value, promoted only by a human in the review
    form, never on a customer resource;
  - the **`listing` quarantine** (D12): price-research pages are stored as
    `listing` documents, excluded from re-ingestion deletion and from the
    RAG knowledge base — dated asking prices never become timeless prose.
- `README.md` — extend, don't rewrite:
  - CLI reference rows for `app catalogue set-identity`,
    `app catalogue render-name`, `app catalogue backfill-identity`,
    `app prices research`, `app prices delete` (exact names/flags from the
    Landed decisions of 6.11/6.18/6.22 — replay each first);
  - the **single** new config key `USED_PRICE_MAX_AGE_DAYS` (int, default
    180, in `.env.dist`) — there is no other new key this phase.
- `docs/demo-walkthrough.md`: a new identity + price chapter — one
  imported suggestion reviewed (claim beside finding, "use the claim",
  approval refused while incomplete), then `app prices research` on an
  approved bike and the snapshot appearing on the detail page and in a
  chat cost answer.
- `docs/core-requirements-checklist.md`: map the new machinery onto the criteria it
  serves (structured retrieval via type codes, tool-result additions,
  provenance display, security posture of D8).
- `docs/model-naming.md`: cross-links to the landed implementation
  (shared-knowledge D1–D5, the display spec, the new CLI) — links only,
  no content rewrite of the domain doc.
- **Three honesty requirements, each explicit in the text:**
  1. the used-price figure is a **published-price snapshot** — whatever
     pages the search provider surfaced — not a classifieds sample; state
     the D8 robots/ToS posture (no constructed listing URLs, robots.txt
     honoured with a visible skip, honest User-Agent) and that
     `sample_count` NULL means unknown, never zero;
  2. fencing remains a **mitigation, not a proof** — the existing
     "Known limitations & future work" entry in `README.md` **stays**
     (D7; do not soften it because 6.14 landed);
  3. the Phase-4 OQ2 guessed prices (BMW S 1000 XR, Honda CB500F, Suzuki
     GSR600) may be described as researched **only** for models
     `app prices research` has actually been run on — check
     `motorbike_used_prices` in the dev DB before writing any such claim,
     and keep the "guessed, owner-approved" wording for the rest.

## Verification

- A reader can execute every documented command verbatim from a fresh
  shell (spot-replay them all); links resolve; `git grep` shows no wording
  that presents guessed prices as researched and no deleted
  known-limitations entry.

## Risks / notes

- Write against **landed** behaviour only — if a documented command's
  output deviates from a Landed decisions entry, that is a report to the
  coordinator, not a silent doc-fix.
- `docs/demo-walkthrough.md`'s existing chapters stand; append, don't
  restructure (the 5.15/5.16 precedent).
- Append (`### Step 6.29`) to `shared-knowledge.md` only if a documented
  behaviour was found to deviate from a landed decision.
