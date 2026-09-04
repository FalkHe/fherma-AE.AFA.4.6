# Phase 5 — Hardening and submission

**Goal:** Make the app grading-ready — close audited error-handling, validation
and prompt-injection gaps, seed a demo catalogue, and document everything so a
fresh clone reproduces the demo.

## Delivered

- **No unhandled error leaks internals** — one catch-all handler returns the
  JSON:API envelope (`internal-error`, generic sentence); tracebacks go to the
  log only (5.4).
- **Six audited validation gaps closed** — filter list caps, catalogue numeric
  plausibility bounds, `page[number]` cap, ULID-shaped chat ids, draft-spec
  dictionary caps, and a 1024-char login password cap (bounds hashing cost per
  attempt) (5.5).
- **LLM calls can no longer hang** — explicit timeouts and retry ceilings on the
  chat and embeddings clients; a gateway timeout routes into the retry budget
  then the apology. Live-proved: an invalid API key ends a turn in ~1 s instead
  of a ~10-minute stall (5.6).
- **Prompt-injection fencing on all advisor surfaces** — retrieved passages,
  preference values and translation context wrapped in sentinel markers, with
  prompt prose stating "data, never instructions"; helpers in one module
  (5.7, 5.8). Live-verified against a poisoned document.
- **One shared untrusted-Markdown renderer** — chat, catalogue detail and admin
  document views, raw HTML permanently off with no per-call-site override
  (5.12).
- **UI failure surfaces completed** — backlog transition snackbar, loading/error
  states on the review tabs, operations warning banner, app-level error boundary
  replacing the white screen (5.13, 5.14).
- **Optional Langfuse tracing** — config-gated callback factory plus a
  self-hosted Compose stack; the default stack starts the same five services as
  before (5.9, 5.10).
- **One-command demo catalogue** — `app seed demo [--auto-approve]` ingests 12
  curated models through the real pipeline, skipping what exists and continuing
  past individual failures; live-run twice (5.11).
- **Submission documentation** — README gained a CLI reference, seed
  instructions, Langfuse and an honest limitations list; a grading map tied every
  criterion and claimed bonus to real files/endpoints/screens; the demo
  walkthrough became seed-aware and gained a submission chapter (5.15, 5.16).
- **Two QA acceptance gates** — security/error pass, plus a fresh-clone run
  following the README verbatim through seed and walkthrough (5.17, 5.18).

## Non-obvious decisions

- **Hardening only, zero schema changes** — the phase confirmed and tested
  already-landed behaviour rather than rebuilding it. No migration was permitted
  at all, which itself ruled out per-stage ingestion failure recording.
- **One new dependency and three config keys for the whole phase** — a
  deliberate budget to keep the submission surface small; the frontend added
  none.
- **Fencing wraps what the model reads, not what is stored** — a tool-level
  "model view" hook keeps persisted results and UI sources byte-identical.
  Dropping the surface was rejected: retrieved passages are the main injection
  vector.
- **Langfuse traces individual LLM calls only** — per-turn grouping and tool
  spans would need advisor rewiring; embeddings emit no callback events.
  Documented honestly rather than engineered further, since the owner declared
  Langfuse nice-to-have.
- **Error surfacing stays per screen** — a global error-to-snackbar middleware
  was overruled by the landed empty-state-plus-retry pattern, which would
  otherwise double-report every failure.
- **Seeded approval is labelled bulk convenience** — `--auto-approve` runs the
  real transition service, never a direct status write, and the walkthrough
  still demos one live admin review so "admin-verified" is earned.
- **Operational lesson pinned as a hard rule** — a profile-scoped teardown
  wiped the shared development database, because `docker compose down` is never
  scoped by profile. Recovery was cheap only because the seed command had
  shipped as code.

## Not delivered / deferred

- **Concurrent-turn 409 race** — out of scope (would change a Phase 3 contract);
  documented as a known limitation, owner decision pending.
- **Per-turn Langfuse grouping and tool spans** — accepted gap, unscheduled.
- **Spec-extraction data quality** — inconsistent manufacturer names (fixed in
  Phase 6) and `a2Eligible` not cross-checked against power (owner decision
  pending).
- **`make langfuse-down` tearing down the whole stack** — found during the docs
  step, fix deferred; README points at the scoped stop command.
- **Shipped as-is** — no token streaming, English only, no rate limiting,
  re-embed progress on the CLI only.
