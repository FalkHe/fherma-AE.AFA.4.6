---
phase: 5
step: "5.13"
title: Error-surface gap closure + AppErrorBoundary
summary: Close the audited UI gaps per ui-spec §3 — backlog transition-error Snackbar, review tab panels own their query loading/error states, operations-failure warning Alert — plus one app-level ErrorBoundary; six new i18n keys; pinned silences stay silent.
effort: 3
dependencies: []
---

# Step 5.13 — Error-surface gap closure + `AppErrorBoundary`

**Effort: 3** — four contained changes with tests, each against an exact
ui-spec pin; no new visual language, no layout changes.

Binding contract: `docs/roadmap/stage-01/phase-5/shared-knowledge.md` (D9) and
**`docs/roadmap/stage-01/phase-5/ui-spec.md` §3, §5, §6, §7** (component, props,
placement, i18n keys, a11y — the truth; this file only sequences). Agent:
**frontend-dev**. Zero deviations — a deviation is a stop-and-report.

**Environment:** no backend code needed; the stack up helps for visual
checks only.

## Outline

- **Gap (a)** — `AdminBacklogRoute`: 6000 ms error Snackbar on
  `useTransitionProduct` failure (ui-spec §3.1 — cloned from the landed
  ConsultationsRoute pattern; success stays surface-free; this is a scoped,
  pinned supersession of the Phase-2 "SSE shows the outcome" rule for HTTP
  failures only).
- **Gap (b)** — `ModelDocumentsPanel` / `ModelImagePanel`: own-query loading
  (`role="status"` spinner) and error (EmptyState + retry) branches instead
  of returning `null` (ui-spec §3.2).
- **Gap (c)** — backlog operations-query failure: conditional
  `severity="warning"` Alert above the table with retry (ui-spec §3.3);
  healthy page byte-identical.
- **Gap (d)** — `AppErrorBoundary` (new
  `frontend/src/components/AppErrorBoundary.tsx`, class component) mounted
  once around `<App />` inside the providers in `frontend/src/main.tsx`
  (ui-spec §5): EmptyState fallback + full-page reload action; render
  crashes only — **never** query errors (no TanStack `throwOnError`).
- i18n: exactly the six keys of ui-spec §6 into
  `frontend/src/locales/en/translation.json` (typecheck enforces them).
- Tests: per ui-spec §3/§5 — panels' error/loading branches, Snackbar on
  transition failure, operations-warning Alert, boundary fallback render.
- **Do not touch** (pinned deliberate silences, ui-spec §3.7/§9): logout
  failure, re-embed operations invisibility, LiveConnectionAlert absence on
  catalogue screens, keystroke validation.

## Verification

- `pnpm lint && pnpm typecheck && pnpm test` green.
- Manual: throw inside a component behind a dev flag → boundary fallback +
  working reload; kill the backend → backlog shows the operations warning;
  failed transition (e.g. offline) → Snackbar.

## Risks / notes

- Reuse the existing `EmptyState`/`Alert`/`Snackbar` idioms verbatim — no
  new shared snackbar infra (no notistack; the two-plus-one local uses stay
  local).
- Append (`### Step 5.13`) to `shared-knowledge.md`: anything QA needs to
  reproduce the new states (dev-flag mechanics, exact aria labels).
