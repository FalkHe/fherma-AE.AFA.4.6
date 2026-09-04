# Phase 5 — Open Questions

Unresolved issues blocking or endangering pinned Phase-5 contracts. Each
entry carries the surrounding knowledge an agent needs to resolve it.
**Resolved questions are removed from this file** and their outcome is
pinned in [`shared-knowledge.md`](shared-knowledge.md).

---

*(none open, 2026-08-28 — all slicing-time questions resolved by the owner
the same day; see below)*

---

## Resolved by owner (2026-08-28) — recorded for the audit trail

- **A1 (uncommitted working tree):** owner approved committing the stray
  CORS change (`backend/app/main.py`, adds `http://127.0.0.1:5173`) as a
  standalone chore commit before dispatching 5.4. **Done — committed at
  slicing end.**
- **OQ-A (`LoginRequest` password length cap):** **approved** — the Phase-1
  "login deliberately unvalidated" pin is relaxed for exactly one bound:
  `LoginRequest.password` gains `max_length=1024` (caps Argon2 work per
  attempt; violation → default 422). Pinned as D2 item 6; lands in 5.5.
  Username handling and the 401-for-wrong-credentials behaviour are
  unchanged; no other login rule may be added. (Side note kept for the
  record: there is no request body-size cap either — a reverse proxy would
  own that in production; out of scope.)
- **OQ-B + OQ-C (Langfuse compat risk & self-hosted stack weight):** owner
  is **indifferent to Langfuse** ("don't care") — it stays in the plan as a
  bonus attempt (5.9 → 5.10), but the coordinator is pre-authorized to drop
  5.10 or all of Langfuse on any friction (failed compat spike, infra
  quirks, time pressure) without another owner round-trip. No fallback
  engineering (SDK pinning hunts, cloud-only rework) is to be spent. If
  dropped: M2 collapses, the grading map omits the logging/monitoring bonus
  claim, 5.15 omits the Langfuse section. Pinned in D5/D6.

---

## Opened during Phase 5

- **Ingestion spec-quality: `a2Eligible` is not cross-checked against
  power** (found 2026-08-29 during the 5.16 walkthrough replay). The
  extraction marked Suzuki GSR600 `a2Eligible: true` at 72 kW, far above the
  35 kW A2 ceiling. The advisor behaved correctly — the strict search
  returned nothing and it offered to widen — so this is a **data-quality**
  issue, not a retrieval or agent bug, and it is out of Phase-5 scope
  (hardening, zero feature work). Candidate fix for a later phase: a
  derived-consistency validator in extraction (power > 35 kW ⇒ `a2Eligible`
  cannot be true), or dropping the extracted flag in favour of deriving it
  from power at query time. Owner decision needed on which.
  **Update (2026-08-29, step 5.18 fresh-clone run):** did **not** reproduce —
  the same bike extracted `a2Eligible: false` at 68 kW on a clean ingestion.
  So this is non-deterministic extraction noise rather than a systematic bug,
  which argues for the derived-consistency validator (cheap, catches the noise)
  over reworking the field. Still owner's call; severity is lower than filed.

- **Ingestion spec-quality: manufacturer names are inconsistent** (found
  2026-08-29 during the 5.18 seed run). The pipeline extracted `Kawasaki` for
  the Z400 and Z900 but `Kawasaki Motors` for the Versys 650, and the same
  risk exists for `Honda` / `Honda Motor`. Consequence: the catalogue's
  Manufacturer filter splits one marque across two entries. Out of Phase-5
  scope (hardening, zero feature work). Candidate fixes for a later phase:
  normalise against a known-marque list at extraction time, or fuzzy-merge
  manufacturers in the review flow so an admin resolves the split before
  approval. Owner decision needed.

  **Closed 2026-08-31, Phase-6 step 6.16.** `manufacturer_service.normalize_name`
  now maps a case-insensitive, first-word marque prefix
  (`backend/app/services/known_marques.py::KNOWN_MARQUES`) onto its canonical
  spelling, so `"Kawasaki Motors"`/`"Honda Motor"` collapse onto `"Kawasaki"`/
  `"Honda"` for every caller by construction. By the time this landed the dev
  DB's split had already self-resolved (all three Kawasaki rows were already
  on the single canonical `Kawasaki` manufacturer; no `Kawasaki Motors` row
  existed to merge) — verified live with `app catalogue set-manufacturer
  kawasaki-versys-650 "Kawasaki Motors"`, which re-pointed to the existing
  `Kawasaki` row without growing `manufacturers`. See
  `../phase-6/shared-knowledge.md` § Landed decisions, Step 6.16.

---

## Carried over (tracked elsewhere, listed for visibility)

- **Q4 / Phase-4 OQ4 — concurrent-turn 409 race:** owner decision still
  pending (fix requires a Phase-3 pin change). **Out of Phase-5 scope by
  hard rule**; documented as a known limitation in 5.15 and left open in
  `../phase-3/open-questions.md` / `../phase-4/open-questions.md`.
- **Phase-4 OQ2 follow-up — guessed demo prices:** the seeded
  `msrp_eur`/`price_band` values on the 3 original models are
  owner-approved guesses. Phase-5 docs must not present them as verified
  (D8); replacing them with researched prices via the Phase-2 review flow
  remains deferred past Phase 5 unless the owner schedules it.
- **Phase-3 N2 — admin AppBar overflow at 390 px:** substantially mitigated
  by the 4.11 fixes (icon-only nav below `sm`, measured fit with headroom at
  360 px, commit `c7340a3`) but never formally re-verified as N2. 5.17's
  state-matrix pass includes a 360/390 px overflow check on admin screens;
  on pass, mark N2 resolved in `../phase-3/open-questions.md`.

---

## Resolved at slicing time (2026-08-28) — recorded for the audit trail

- **`backend/app/api/errors.py` (old 5.1 outline) vs the Phase-2
  one-handler pin:** the pin wins — only a 500 catch-all was missing; it
  registers in `main.py` (D1). No new module.
- **Per-stage ingestion failure recording (old 5.1):** superseded by the
  pinned Phase-2 policy ("a partial failure is a warning, never a failure"),
  the existing stage milestones/warnings/abandon-to-backlog/retry button,
  and the zero-migrations hard rule. No step.
- **New LLM exception taxonomy (`LlmUnavailableError`, `LlmOutputError`,
  old 5.1):** unnecessary — the landed taxonomy (`MissingApiKeyError`,
  `TransientJobError` + `TRANSIENT_GATEWAY_ERRORS`, `EmptyAnswerError`,
  typed ingestion failure reasons, the apology path) already covers it; the
  real gap was client timeouts → D3/5.6.
- **`.env.example` (old 5.3):** the template is **`.env.dist`** — README,
  compose.yaml and the file itself already say so.
- **`docs/demo-script.md` (old 5.3):** superseded by the 4.10 landed
  decision — 5.16 extends `docs/demo-walkthrough.md`.
- **Seed vs walkthrough counts:** the seed invalidates the walkthrough's
  hard-coded 3-model counts/ULIDs → 5.16 makes it count-agnostic.
- **Frontend "error middleware → snackbars" (old 5.1) and "TanStack Query
  error boundaries" (old 5.2):** superseded by the landed per-screen
  EmptyState + refetch pattern (D9, ui-spec §9); one app-level
  `AppErrorBoundary` for render crashes only.
- **"Reconnecting…" indicator (old 5.2):** already landed
  (`LiveConnectionAlert`, 5 s grace); catalogue omission re-confirmed.
- **Re-embed job status in the UI (old 5.2):** pinned deliberate omission
  (ui-spec §3.7) — CLI-triggered job, CLI is the progress surface; named in
  the 5.15 limitations.
- **Langfuse on embeddings (old 5.2):** excluded — LangChain embeddings emit
  no callback events; documented limitation (D5).
- **Embeddings client timeout:** step 3.9's "out of scope" marker expired —
  5.6 owns `llm/embeddings.py` now (D3).
- **Backlog transition-error visibility:** the Phase-2 "SSE shows the
  outcome" pin is superseded **for HTTP failures only** (designer decision,
  ui-spec §3.1) — a 6000 ms error Snackbar; success stays surface-free.
- **Shared markdown consolidation:** the rule-of-three threshold is reached
  (3 duplicated sites) — `UntrustedMarkdown` (D9, ui-spec §4); the Phase-3/4
  "deliberately not shared" notes are superseded.
