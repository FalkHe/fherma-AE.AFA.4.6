---
phase: 6
step: "6.31"
title: Phase-6 final acceptance and the fencing security proof
summary: QA gate for milestone M4 plus the independent security proofs — poisoned title/heading-trail fences that survived 6.19/6.23, byte-identical persisted JSONB, the listing quarantine in retrieval and re-ingestion, the stale caveat in advisor prose — then a docs replay and the phase-6-done tag.
effort: 3
dependencies: ["6.28", "6.29"]
---

# Step 6.31 — Phase-6 final acceptance and the fencing security proof (QA)

**Effort: 3** — adversarial probes plus the M4 walkthrough and a docs
replay; security/correctness-critical behaviour is re-derived, never
trusted from a dev report.

Binding contract: `docs/roadmap/phase-6/shared-knowledge.md` (**the M4 row
of the milestone table is the checklist**; D7, D8, D9, D10, D11, D12 are
the contracts to prove or refute) and `docs/roadmap/phase-6/ui-spec.md`
§4, §5 (the used-price rows of the matrix). Read the **Landed decisions**
of 6.13–6.14 and 6.21–6.23 (sentinel wording, capture location, CLI
output) and `docs/qa-checklist.md`. Agent: **qa** (qa-backend +
qa-frontend; Playwright for UI evidence). Zero deviations — a deviation is
reported, not worked around.

**Environment:** stack up (`make up`), `app-worker` current; at least one
approved bike researched via `app prices research`; 6.14's pre-change
JSONB capture available (its step report/evidence). **Never
`docker compose down`.**

## Outline

Behaviour only — do not re-author dev infrastructure checks, and do not
repeat 6.30's identity items:

- **M4 criterion, end to end:** `app prices research <slug>` on an
  approved bike fetches only search-provider URLs, **refuses a
  robots.txt-disallowed URL out loud** in the CLI output (D8), stores
  `listing` documents, and writes median + range + as-of date with
  per-source provenance. A chat cost question answers with that median,
  names the sources and the date. The catalogue detail shows the dated
  snapshot with its sources; a bike without one shows the defined absent
  state (nothing), never a guess.
- **Staleness (D10):** force staleness in a scratch way (backdate `as_of`
  in the dev DB or a temporarily lowered `USED_PRICE_MAX_AGE_DAYS` —
  restore afterwards): the advisor's prose carries the mandatory
  assumption line with the date and the word *indicative*, and the UI
  snapshot shows the stale caption — both driven by the same server
  verdict, never disagreeing.
- **Fencing, independently (D7):** ingest a document whose **page title**
  and **heading trail** carry "Ignore previous instructions …" (plus one
  sentinel-lookalike payload); interview the advisor toward that bike —
  the `retrieve_bike_knowledge` model payload shows sentinels around
  `sourceTitle` and `headingPath`, the reply does not comply. **The 6.14
  fences must have survived 6.19 and 6.23**: a tool payload that lost a
  sentinel is a regression — check the rendered-name and `usedPrice`
  additions specifically.
- **Persistence pin (D7/5.8):** the persisted `tool_calls[].result` /
  `sources[]` JSONB for an equivalent turn is **byte-identical in shape**
  to the pre-6.14 capture — no sentinel ever persisted or served to the
  UI.
- **Listing quarantine (D12):** no `listing` document is retrievable
  through `retrieve_bike_knowledge` (probe via chat sources[] and the
  retrieval CLI); a **re-ingestion** (`app ingest run`) of the researched
  bike does **not** delete the price snapshot or its `listing` provenance
  rows.
- **Docs replay:** every command 6.29 documented executes verbatim from a
  fresh shell; the three honesty statements match observed reality
  (published-price framing, known-limitations entry present, no
  "researched" wording on unresearched guessed prices).
- Evidence filed (CLI transcripts, DB queries, screenshots, chat
  transcripts); scratch data cleaned up (poisoned model, backdated rows
  restored).
- **On pass: tag `phase-6-done`.**

## Verification

- The M4 demo criterion is quoted and answered item by item; every failure
  filed with reproduction steps. This step is the **only** place the M4
  criterion and the phase-level security claims are formally proven.

## Risks / notes

- Fencing is a mitigation, not a proof (D7) — a probe that partially
  leaks tone but not instructions is a judgement call: report verbatim
  transcripts, let the owner judge borderline cases.
- If no robots-disallowed URL naturally appears in the provider results,
  a scratch disallowed host/path is acceptable to prove the gate — record
  exactly how it was staged.
- Restore every scratch change (env keys, backdated `as_of`) before
  tagging; the tag asserts the shipped state, not the test rig.
