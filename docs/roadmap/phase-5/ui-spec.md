# Phase 5 — UI Specification: Hardening & polish audit

**Binding for the Phase-5 frontend work in steps 5.1 and 5.2.** This is an
audit-and-close-gaps spec, not a screen spec: Phase 5 adds **no screens, no
redesigns, no layout changes and no dependencies**. Everything below either
(a) confirms an existing pinned state as already correct, (b) closes a named
gap with the smallest surface that reuses a landed pattern, or (c) re-pins a
deliberate omission with its rationale.

Read first: the Phase-2/3/4 ui-specs
([`../phase-2/ui-spec.md`](../phase-2/ui-spec.md),
[`../phase-3/ui-spec.md`](../phase-3/ui-spec.md),
[`../phase-4/ui-spec.md`](../phase-4/ui-spec.md)) — their pinned state rules
are the baseline being audited and **remain binding unchanged** except where
§3 explicitly supersedes them — plus each phase's `shared-knowledge.md`
"Landed decisions". Where this spec and a phase's shared-knowledge disagree,
report the conflict, don't build either version.

Shared conventions (all prior phases' conventions continue to apply):

- MUI stock components only, palette tokens only, Material Symbols via
  `<Icon>` — no `@mui/icons-material`, **no notistack, no new dependency of
  any kind** (§10 R7).
- All new strings via `t()`; full key list in §7. Compile-time-checked keys —
  every new key lands in `frontend/src/locales/en/translation.json`.
- Error rendering branches on **HTTP status + error `code` only, never on
  `detail` text** (landed pin). The backend adds a global 500 catch-all this
  phase returning the JSON:API envelope with a generic-500 code (exact code
  name may still shift): **no frontend change follows from it** — every
  landed error surface already renders `common.errors.serverError` for
  unmapped statuses, and nothing may start rendering envelope `detail` text.
- Forms validate **on submit only** (landed pin) — step-5.1's "inline field
  errors" are already landed in exactly that shape; no keystroke validation
  is added (§10 R2).
- Markdown: `react-markdown` + `remark-gfm`, raw HTML **off — never add
  `rehype-raw`**. Phase 5 consolidates the three duplicated configurations
  into one shared component (§4).

---

## 1. Scope of the audit

Frontend files this phase touches (complete list — anything else is out of
scope for the frontend steps):

| File | Change | Section |
|---|---|---|
| `frontend/src/components/UntrustedMarkdown.tsx` | **New** — shared markdown renderer | §4 |
| `frontend/src/components/UntrustedMarkdown.test.tsx` | **New** — shared inertness/config tests | §4.4 |
| `frontend/src/components/MessageBubble.tsx` | Migrate to `UntrustedMarkdown` | §4.3 |
| `frontend/src/components/MessageBubble.test.tsx` | Gap (f): raw-HTML inertness test | §3.6 |
| `frontend/src/components/ModelDocumentsPanel.tsx` | Migrate to `UntrustedMarkdown`; gap (b) states | §4.3, §3.2 |
| `frontend/src/routes/CatalogueModelRoute.tsx` | Migrate to `UntrustedMarkdown` | §4.3 |
| `frontend/src/components/ModelImagePanel.tsx` | Gap (b) states | §3.2 |
| `frontend/src/routes/admin/AdminBacklogRoute.tsx` | Gap (a) Snackbar, gap (c) Alert | §3.1, §3.3 |
| `frontend/src/components/AppErrorBoundary.tsx` | **New** — gap (d) | §5 |
| `frontend/src/main.tsx` | Mount the boundary | §5 |
| `frontend/src/routes/RegisterRoute.tsx` | No change — test only | §3.5 |
| `frontend/src/routes/RegisterRoute.test.tsx` | **New** — gap (e) | §3.5 |
| `frontend/src/locales/en/translation.json` | §7 keys | §7 |

---

## 2. Screen × state audit matrix (doubles as the QA walkthrough checklist)

Legend: **OK §n** = already pinned and landed per the cited prior ui-spec
section, verify unchanged; **Δ §n** = Phase 5 changes it per the cited
section of *this* spec; **n/a** = the state does not exist on that screen;
**pinned omission** = deliberate absence, re-confirmed in §3/§10.

| Screen | Loading | Empty | Error | In-progress | Reconnect |
|---|---|---|---|---|---|
| Login / Register | n/a (form) | n/a | OK — submit-only field errors + status/code mapping (Phase-1; **Δ §3.5** adds the missing Register test) | OK — pending submit button spinner | n/a |
| Consultations list | OK P3 §4 (4 skeleton rows) | OK P3 §4 (`forum` EmptyState → CTA) | OK P3 §4 (EmptyState + retry; create-error Snackbar) | OK P3 §4 ("Advisor is replying…" caption) | pinned omission (P3 §10 — list degrades gracefully) |
| Consultation chat | OK P3 §5 (`role="status"` spinner) | OK P3 §5 (fresh-chat typing / idle intro) | OK P3 §5 + §3.3 (404 / 5xx EmptyState; failed-send bubble; stale-turn row) | OK P3 §2.2/§3.3 (seen → typing… → message) | OK — `LiveConnectionAlert` above composer (P3 §2.3) |
| Catalogue list | OK P4 §3.7 (8 skeleton cards) | OK P4 §3.7 (empty vs no-match branches) | OK P4 §3.7 (EmptyState + retry) | OK P4 §3.1 (reserved `LinearProgress` slot on refetch) | pinned omission (P4 §2.2) |
| Catalogue detail | OK P4 §4.6 (full-shape skeletons) | OK P4 §4.2–4.5 per-block fallbacks | OK P4 §4.6 (404 / 5xx EmptyStates); prose via **Δ §4** shared component (byte-identical) | n/a | pinned omission (P4 §2.2) |
| Admin backlog | OK P2 §4 (5 skeleton rows) | OK P2 §4 (empty vs filtered branches) | OK P2 §4 list error; **Δ §3.1** transition-error Snackbar; **Δ §3.3** operations-error Alert | OK P2 §3.1 (`OperationProgress` per row, SSE-driven) | OK — `LiveConnectionAlert` in `AdminLayout` (P3 §2.3) |
| Admin review — page shell | OK P2 §6 (spinner gate, 404/5xx EmptyStates, status gates) | OK P2 §6 | OK P2 §6 (transition errors in `ConfirmDialog.hasError`) | OK P2 §6 (ingesting gate shows `OperationProgress`) | OK — `AdminLayout` |
| Admin review — Documents tab | **Δ §3.2** (was: `null` → blank tab) | OK P2 §7 EmptyState | **Δ §3.2** (was: `null` → blank tab) | n/a | OK — `AdminLayout` |
| Admin review — Specs tab | OK P2 §8 (route gate; form renders from loaded product) | OK P2 §8 | OK P2 §8 (submit-only field errors + save Snackbar) | OK P2 §8 (pending save button) | OK — `AdminLayout` |
| Admin review — Image tab | **Δ §3.2** (was: `null` → blank tab) | OK P2 §9 EmptyState | **Δ §3.2** (was: `null` → blank tab); reject error in dialog OK | n/a | OK — `AdminLayout` |
| Whole SPA (render crash) | — | — | **Δ §5** `AppErrorBoundary` (was: white screen) | — | — |
| Re-embed operations (`entityId: null`) | — | — | — | **pinned omission** — §3.7 | — |

---

## 3. Gap closures

### 3.1 Gap (a) — backlog transition error becomes visible (supersedes a Phase-2 pin)

Phase-2 shared-knowledge pinned the `useTransitionProduct` start/retry
ingestion error as invisible ("SSE shows the outcome"). That pin only holds
for **accepted** transitions — a rejected or failed HTTP request emits no
SSE event, so today nothing on the page changes and the click looks ignored.
**Superseded for the failure case** (§10 R6); success stays surface-free.

Fix in `AdminBacklogRoute` — the exact `ConsultationsRoute` create-error
pattern (same props, same rationale comment style):

```tsx
<Snackbar open={transition.isError} autoHideDuration={6000}
          onClose={() => transition.reset()}>
  <Alert severity="error" onClose={() => transition.reset()}>
    {t("admin.backlog.transitionError")}
  </Alert>
</Snackbar>
```

Rendered as the last sibling in the route's fragment (after the
`AddModelDialog` block). One Snackbar covers both "Start ingestion" and
"Retry ingestion" — same mutation, same message. No per-row surface, no
layout change. Not applied to `AdminModelReviewRoute`'s transitions — those
already surface errors via `ConfirmDialog.hasError` (matrix row above).

**Test hook:** mutation endpoint stubbed to 500 → Snackbar with
`admin.backlog.transitionError` appears; row unchanged; alert dismissible.

### 3.2 Gap (b) — review tab panels own their query's loading/error states

`ModelDocumentsPanel` (`useProductDocuments`) and `ModelImagePanel`
(`useProductImage`) currently `return null` while their own query is
unsettled *or failed* — the route only gates the product query, so a failed
tab is indistinguishable from an empty one. Replace the single
`data === undefined → null` branch in **both** panels with two branches, in
this order:

1. **Error** (`query.isError`) — the landed EmptyState-plus-retry pattern:

   ```tsx
   <EmptyState icon="error"
     title={t("admin.review.documents.loadError")}   // image: admin.review.image.loadError
     body={t("common.errors.serverError")}
     action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
   ```

2. **Loading** (`data === undefined`, not error) — the pinned Phase-1 guard
   markup, tab-panel sized:

   ```tsx
   <Box role="status" aria-label={t("common.loading")}
        sx={{ display: "flex", justifyContent: "center", py: 8 }}>
     <CircularProgress size={48} />
   </Box>
   ```

The existing empty branches (P2 §7/§9 EmptyStates) stay exactly as landed.
No change to the panels' loaded rendering.

**Test hooks:** per panel — query stubbed to fail → EmptyState with retry,
retry refetches and a success renders content; query pending → `role="status"`
present, no EmptyState.

### 3.3 Gap (c) — operations query failure surfaces on the backlog

When `useLatestOperationsByEntity` fails, every progress cell silently
disappears while status chips still say "ingesting" — stale-looking data
with no explanation. Minimal surface in `AdminBacklogRoute`, rendered
between the toolbar `Stack` and `renderContent()` **only when
`operations.isError`** (no reserved slot — the healthy page is unchanged):

```tsx
{operations.isError && (
  <Alert severity="warning" icon={<Icon>sync_problem</Icon>} sx={{ mb: 2 }}
         action={<Button color="inherit" size="small"
                         onClick={() => void operations.refetch()}>
                   {t("common.retry")}
                 </Button>}>
    {t("admin.backlog.operationsLoadError")}
  </Alert>
)}
```

Same visual language as `LiveConnectionAlert` (warning + `sync_problem`):
both mean "the table is still right, its liveness is not". The
`useOperations` hook's "no screen branches on why" doc comment is updated to
name this one consumer branch (`isError`, never the error value). Progress
cells keep rendering nothing on failure — the Alert is the one surface.

**Test hook:** operations endpooint stubbed to fail, products succeeding →
rows render, warning Alert present, retry refetches.

### 3.4 Gap (d) — app-level ErrorBoundary

Built — see §5. (Judgement: worth having. A React render crash currently
white-screens the SPA with no recovery affordance; one boundary with a
reload action is ~40 lines and closes it. Per-route boundaries are not built
— a render crash is a bug to fix, not a state to design per screen.)

### 3.5 Gap (e) — `RegisterRoute` test

No component change. Add `frontend/src/routes/RegisterRoute.test.tsx`
mirroring `LoginRoute.test.tsx`'s structure (renderWithProviders + the
`network.ts` fetch stubs). Must cover, all submit-triggered (validation on
submit only — the landed pin):

- successful registration → the landed post-register navigation/identity
  behaviour;
- client validation: invalid username → `auth.errors.usernameInvalid`;
  short password → `passwordTooShort`; mismatch → `passwordMismatch`; no
  request is sent in these cases;
- 409 username-taken (branch on status + code, never detail) →
  `auth.errors.usernameTaken` on the field;
- 500 → `auth.errors.serverError`;
- no error text rendered from the response envelope's `detail`.

### 3.6 Gap (f) — `MessageBubble` raw-HTML inertness test

Add to `MessageBubble.test.tsx` the same assertion the catalogue and admin
document tests already carry: an assistant message whose body contains
`<script>alert(1)</script>` and `<img src=x onerror=alert(1)>` renders both
as **literal text**; the DOM contains no `script` or `img` element from the
body; a markdown link renders with `target="_blank"` and
`rel="noopener noreferrer"`. (The shared component gets its own copy in
§4.4 — this per-site test additionally proves the *chat* wiring passes
untrusted content through it.)

### 3.7 Gap (g) — re-embed operations: **pinned deliberate omission**

Re-embed jobs (`entityId: null`) stay invisible in the admin UI.
Rationale: re-embedding is triggered from the **CLI only** (Typer command)
— no admin screen offers the action, so a status surface would be an orphan
readout with no cause the UI can show; the CLI run itself is the operator's
progress surface. `latestByEntity` skipping `entityId === null` rows stays
as landed. A "background jobs" panel would be a new screen element —
excluded by this phase's charter. Step-5.2's "re-embed job status" wording
is resolved against this pin (§10 R5); note the omission in step 5.3's
limitations section.

---

## 4. `UntrustedMarkdown` — the one markdown renderer

### 4.1 Why

The pinned react-markdown configuration (GFM, raw HTML off, `ExternalLink`
anchors, bordered-table `sx`) is duplicated at three sites — `MessageBubble`,
`CatalogueModelRoute`, `ModelDocumentsPanel`. Rule of three reached (the
catalogue file's own "a shared module is a rule-of-three decision" comment
called this); three copies of a **security-relevant** config is three places
to get it wrong. Consolidate; **rendering at all three sites stays
byte-identical** — the shared base is exactly the intersection of the three
configs, every delta stays site-local.

### 4.2 API — `frontend/src/components/UntrustedMarkdown.tsx`

```tsx
import type { Components } from "react-markdown";
import type { SxProps, Theme } from "@mui/material/styles";

/**
 * Renders retrieved/LLM-generated markdown, inert by construction: GFM only,
 * raw HTML off. Never add `rehype-raw`; no plugin props are exposed, so no
 * call site can turn raw HTML on.
 */
export function UntrustedMarkdown({
  children,
  components,
  sx,
}: {
  /** The markdown string — always server/retrieved content, never user-typed. */
  children: string;
  /** Site overrides merged over the base `{ a: ExternalLink }`. Never pass `a`. */
  components?: Components;
  /** Site-specific typography merged after the base sx. */
  sx?: SxProps<Theme>;
})
```

Implementation pins:

- `import ReactMarkdown from "react-markdown"` (aliased — the component
  itself is named `UntrustedMarkdown`).
- Renders
  `<Box sx={[BASE_MARKDOWN_SX, ...(Array.isArray(sx) ? sx : [sx])]}>` wrapping
  `<ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={{ a: ExternalLink, ...components }}>{children}</ReactMarkdown>`.
- `ExternalLink` (MUI `Link`, `target="_blank" rel="noopener noreferrer"`),
  `REMARK_PLUGINS = [remarkGfm]` and `BASE_MARKDOWN_SX` move here as
  module-level constants; `ExternalLink` is **not exported** (nothing else
  uses it once the three sites migrate).
- `BASE_MARKDOWN_SX` — the exact intersection of the three landed configs,
  verbatim:

  ```ts
  const BASE_MARKDOWN_SX = {
    "& table": { borderCollapse: "collapse", my: 2 },
    "& th, & td": { border: 1, borderColor: "divider", px: 1, py: 0.5, textAlign: "left" },
    "& pre": { overflowX: "auto" },
    "& a": { wordBreak: "break-word" },
  } as const;
  ```

- **No `remarkPlugins`/`rehypePlugins` props** — deliberately not part of
  the API. Adding rehype-raw (or any plugin) requires editing this file and
  its doc comment, which is the point.
- Call sites hoist their `components`/`sx` objects to module constants (as
  all three already do today) — no inline object literals per render.

### 4.3 Migration notes per site (each keeps a module-level delta constant)

| Site | `sx` delta (site constant, merged after base) | `components` delta | Deleted from the site |
|---|---|---|---|
| `MessageBubble` | `{ "& > :first-of-type": { mt: 0 }, "& > :last-child": { mb: 0 }, "& p": { my: 1 } }` | — | local `ExternalLink`, `MARKDOWN_COMPONENTS`, `REMARK_PLUGINS`, base half of `MARKDOWN_SX` |
| `ModelDocumentsPanel` | `{ "& img": { maxWidth: "100%", height: "auto" } }` | — | same |
| `CatalogueModelRoute` | `{ "& p": { my: 1 }, "& img": { maxWidth: "100%" } }` | `{ table: ProseTable, h1: ProseHeading3, h2: ProseHeading3, h3: ProseHeading4, h4: ProseHeading4, h5: ProseHeading4, h6: ProseHeading4 }` — `ProseTable`/`ProseHeading*` **stay in the route file** (catalogue-specific heading demotion, P4 §4.4) | same; the "rule-of-three" comment (now satisfied) |

Usage everywhere:
`<UntrustedMarkdown sx={SITE_MARKDOWN_SX} components={SITE_COMPONENTS}>{markdown}</UntrustedMarkdown>`.

### 4.4 Tests — `UntrustedMarkdown.test.tsx`

- `<script>` and `<img onerror>` in the input render as literal text; no
  `script`/`img` element in the DOM.
- A markdown link renders as an anchor with `target="_blank"` and
  `rel="noopener noreferrer"`.
- A GFM table renders `table`/`th`/`td` elements.
- A `components` override (e.g. a custom `table`) is applied **and** links
  still render through `ExternalLink` (the base `a` survives the merge).

Existing per-site inertness tests (catalogue, admin documents) are **kept**
— they now prove the wiring, the shared test proves the config; §3.6 adds
the missing chat one.

---

## 5. `AppErrorBoundary`

One app-level boundary, no per-route boundaries. File
`frontend/src/components/AppErrorBoundary.tsx`:

- A class component (React requires a class for `componentDidCatch` /
  `getDerivedStateFromError`; this is stock React, not a new dependency).
  `componentDidCatch` logs via `console.error`; state is
  `{ hasError: boolean }` — the error object is not rendered (never leak
  internals to the screen; same principle as the backend's generic 500).
- Fallback (children swapped out wholesale) — the landed `EmptyState`
  pattern, translated via a small function child so hooks are usable:

  ```tsx
  <EmptyState icon="error"
    title={t("common.errors.crashTitle")}
    body={t("common.errors.crashBody")}
    action={<Button variant="contained" startIcon={<Icon>refresh</Icon>}
                    onClick={() => window.location.reload()}>
              {t("common.errors.crashReload")}
            </Button>} />
  ```

  **Reload, not client-side reset**: after a render crash, in-memory state
  is not trustworthy; a full reload is the honest recovery.
- Mounted in `main.tsx` **around `<App />`, inside** `ThemeProvider`,
  `I18nextProvider`, `QueryClientProvider` and `BrowserRouter` — the
  fallback needs theme + `t()`. Pinned limitation: a crash *in the providers
  themselves* still white-screens; out of scope (that is startup
  configuration, not runtime rendering).
- **Never used for data errors**: query/mutation errors keep their landed
  per-screen surfaces (§10 R3); no `throwOnError` anywhere.

**Test hook:** `AppErrorBoundary.test.tsx` — a child component that throws
during render → fallback with `common.errors.crashTitle` renders and the
reload button is present (stub `window.location.reload`); a healthy child
renders unchanged.

---

## 6. i18n keys (merge into `frontend/src/locales/en/translation.json`)

All new; nothing moves, nothing is deleted. `common.retry`,
`common.loading` and `common.errors.serverError` are reused as pinned.

```json
{
  "common": {
    "errors": {
      "crashTitle": "Something went wrong",
      "crashBody": "An unexpected error broke this page. Reloading usually fixes it.",
      "crashReload": "Reload page"
    }
  },
  "admin": {
    "backlog": {
      "transitionError": "Could not start the ingestion. Please try again.",
      "operationsLoadError": "Ingestion progress could not be loaded — statuses are still current."
    },
    "review": {
      "documents": {
        "loadError": "Could not load the documents"
      },
      "image": {
        "loadError": "Could not load the image"
      }
    }
  }
}
```

---

## 7. Accessibility / UX checklist additions (new surfaces only — all prior checklists still apply)

- **Alerts announce themselves:** MUI `Alert` carries `role="alert"` — the
  transition-error Snackbar (§3.1) and the operations warning (§3.3) are
  announced without focus theft; both offer a real dismissal/retry `Button`,
  never icon-only.
- **Color is never the only signal:** the §3.3 warning pairs `severity`
  color with the `sync_problem` icon and full-sentence text; the boundary
  fallback pairs the `error` glyph with title + body + labelled action.
- **Progress semantics:** the §3.2 tab-panel spinner is `role="status"` with
  the translated `common.loading` label — the pinned Phase-1 guard markup,
  not a new pattern; it replaces only the panel body, never overlays it.
- **Retry is always a real control:** every new error surface (§3.1–3.3, §5)
  exposes a stock `Button` with a translated label — no bare links, no
  auto-retry loops.
- **The boundary fallback keeps the document sane:** `EmptyState` renders an
  `h2` heading; the reload action is a full navigation, so assistive tech
  gets a fresh, consistent document rather than a half-crashed tree.
- **No layout jumps:** §3.1's Snackbar floats; §3.3's Alert renders only in
  the error case (an error state may shift layout — a healthy page never
  reserves space for it, matching the `LiveConnectionAlert` precedent).

---

## 8. Verification hooks (for the QA agent)

The §2 matrix **is** the walkthrough: execute it row by row — throttled
network for loading, fresh account for empty, stopped backend / stubbed 500
for error, live ingestion + a consultation turn for in-progress,
`docker compose stop`-and-start of the backend for reconnect. Additionally:

- Backlog: kill the transition endpoint → Snackbar (§3.1); kill only
  `/api/operations` → rows render + warning Alert with working retry (§3.3).
- Review tabs: fail the documents/image query → EmptyState + retry per tab;
  slow it → `role="status"` spinner, never a blank tab (§3.2).
- Markdown: after migration, visually diff one chat answer with a GFM table,
  one catalogue article (heading demotion + wide-table scroll at 360px), one
  admin document — byte-identical rendering; the poisoned-document scenario
  from step 5.1 renders `<script>`/`<img onerror>` as inert text on **all
  three** surfaces.
- Boundary: force a render throw (dev-only prop or test) → fallback +
  working reload; confirm a plain query error does **not** trip it.
- `pnpm lint`, `pnpm typecheck`, `pnpm test` green; new tests per
  §3.5/§3.6/§4.4/§5 present and meaningful.

---

## 9. Resolutions (audit decisions where step outlines conflicted with landed pins)

**R1 — step-5.1 "map the error envelope via a shared handler in the
openapi-fetch middleware":** overruled by the landed pattern. Error handling
stays **per-screen** (status+code branching in hooks, EmptyState/Snackbar/
field-error surfaces); the middleware keeps exactly its one landed job (401
→ drop cached identity). A global snackbar-per-error handler would
double-report every failure that already has a designed surface.

**R2 — step-5.1 "inline field errors on login/registration/backlog forms":**
already landed, submit-only. Phase 5 adds only the missing `RegisterRoute`
test (§3.5). The submit-only pin wins over any keystroke-validation reading.

**R3 — step-5.2 "TanStack Query error boundaries with a retry action":**
overruled. The landed per-screen `EmptyState` + `refetch` pattern wins; no
`throwOnError`, no query error boundaries. The new `AppErrorBoundary` (§5)
covers **render crashes only** — a different failure class.

**R4 — step-5.2 "a subtle reconnecting… indicator":** already landed as
`LiveConnectionAlert` (chat + `AdminLayout`; 5 s grace). Nothing to build.
The pinned **omission on catalogue screens** (P4 §2.2 — a static read-only
catalogue degrades gracefully) is re-confirmed, not revisited.

**R5 — step-5.2 "re-embed job status":** pinned deliberate omission, §3.7 —
CLI-triggered job, no UI trigger, the CLI is the progress surface.

**R6 — Phase-2 pin "transition errors are invisible; SSE shows the
outcome":** superseded **for the HTTP-failure case only** (§3.1) — a failed
request emits no SSE, so the pin's own rationale doesn't reach it. Accepted
transitions still get no success surface (SSE genuinely shows that outcome).

**R7 — snackbar infrastructure:** not built. Three local `Snackbar` uses
(consultations create-error, specs save-success, §3.1 transition-error) do
not justify a provider, and notistack is a dependency — excluded this phase.
Flag for a future phase only if a fourth appears.

**R8 — markdown consolidation vs the catalogue file's "deliberately not
shared" comment:** that comment itself named rule-of-three as the threshold;
three sites exist, the threshold is met (§4). The comment is deleted with
the migration.
