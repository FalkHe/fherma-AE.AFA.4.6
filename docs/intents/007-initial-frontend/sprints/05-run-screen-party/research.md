---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 007/05 — run screen with party

## Facts

**Frontend only — the read exists.** `GET /api/v1/playthrough/runs/{run_id}/overview`
(`backend/app/modules/playthrough/routes.py:69-77`) answers `CampaignRunOverviewRead`
(`schemas.py:74-94`, generated at `frontend/src/api/schema.d.ts:334-370`):
`id, campaignId, contentVersion, title, status, createdAt, campaignTitle, campaignSummary,
unavailable, members[], adventures[]`. `members[]` is `CampaignRunMemberRead`
(`schema.d.ts:318-333`): `userId, username, role, ready, characterName`. Every AC1/AC2 field is
covered by this one call; no backend change, no `make generate-api`.

Unknown run and someone else's run both raise `CampaignRunNotFoundError`
(`service.py:170-185`) → HTTP 404, envelope code `NOT_FOUND` (`core/errors.py:39,80`) — AC5's
"reads identically" holds server-side already. Run `status` ∈
`setup|ready|active|archived|finished` (`models.py:40`); `role` ∈ `owner` only (`models.py:66`).
`campaignTitle`/`campaignSummary` are `null` exactly when `unavailable` is `true`.

**Routing.** `frontend/src/App.tsx:20-31` — one pathless layout route `RequireAuth` →
`AppShell action={<AccountMenu/>}` wraps `/` and `/dashboard`; `/runs/:runId` is one more `Route`
inside it. `AppShell` (`core/layout/AppShell.tsx:92`) caps content at `Container maxWidth="sm"`
(600px); the design's run and dashboard pages are 1080px
(`docs/design/.../CampaignRun.dc.html:24`), and no test asserts the current width.

**Data pattern.** One hook per operation over TanStack Query: `useCurrentUser`
(`modules/auth/hooks/useCurrentUser.ts:33-48`) returns `{data…, isPending, isError, refetch}` and
turns an expected status code into state rather than an error. Network goes through
`unwrap(api.GET(...))` (`core/api/errors.ts:20`), throwing `ApiFailure {code, status}`. Query
defaults: `retry: false`, `staleTime: 30_000` (`core/queryClient.ts`).
Loading/error/retry precedent: `RequireAuth` (`modules/auth/components/RequireAuth.tsx:42-61`) —
`CircularProgress` + `common:app.loading`, then `Alert severity="error"` + a `common:actions.retry`
button calling `refetch`.

**Module layout.** `modules/<name>/{components,hooks,routes}` + a `README.md`
(`modules/auth/README.md`). `structure.test.ts:154-239` pins `core/`'s file list exactly and allows
`.tsx` only under `core/layout/` — a new locale file under `core/i18n/locales/en/` **must** be added
to that list or the suite fails.

**i18n.** One namespace per module plus `common`, registered in `core/i18n/index.ts:6-12`; keys are
compile-checked (`core/i18n/i18n.d.ts`). `common.json` holds `app.title/app.loading`,
`actions.retry`, `errors.network/unexpected`.

**UI primitives.** None beyond MUI: the sprint-03 theme (`core/theme/index.ts`) supplies palette,
`shape.borderRadiusOrganic|OrganicSoft|Pill`, shadows, typography — no `components:` overrides, so
screens use MUI parts with `sx` and `var(--…)` tokens. All design tokens the run screen needs exist
(`theme/tokens/colors.css`: `--surface-timber`, `--surface-inset`, `--border-timber`,
`--border-hairline`, `--accent-secondary-quiet`, `--moss-300`, `--text-muted`). No hex/rgb literal
may appear under `src` (`structure.test.ts:113`). No dialog/modal exists yet; `@mui/material` 9.4.0
(`frontend/pnpm-lock.yaml:395`) `Dialog` + `DialogTitle/Content/ContentText/Actions` generates its own
`aria-labelledby` through `DialogContext`, and `disableEscapeKeyDown` is gone in v9 — use `onClose`'s
`reason` (@mui/material 9.4.0 — source: context7, docs v9.2.0).

**Tests.** Vitest (`frontend/vitest.config.ts`), jsdom, no globals, `src/**/*.test.{ts,tsx}` beside
the code. `src/test/render.tsx` → `renderApp(["/runs/abc"])`; `src/test/network.ts` →
`mockRoute("GET", "/api/v1/playthrough/runs/abc/overview", {status, body})`; an unstubbed request
throws. Run: `make frontend-test` or `docker compose run --rm --no-deps node-cli pnpm test <path>`.

## Work items

- **WI1 route and read**: new `modules/playthrough` (README, `hooks/useRunOverview.ts`,
  `routes/RunRoute.tsx`), the `/runs/:runId` route in `App.tsx`, the `playthrough` namespace wired
  into `core/i18n/index.ts` and pinned in `structure.test.ts`; owns the back link, document title,
  status badge, campaign title and description, and the loading / retryable-error / not-found states
  (AC1, AC5). Widens `AppShell`'s container to the design's 1080px.
- **WI2 party section**: `components/PartySection.tsx`, `PlayerCard.tsx`, `InviteTile.tsx` — the
  "n of m characters ready" line, one card per member (initial, name, role badge, state box) and the
  invite tile; owns the open/close state both buttons drive (AC2, AC3).
- **WI3 in-development dialog**: `components/InDevelopmentDialog.tsx` with its copy under `common`
  (AC4).

## Interfaces

```ts
// WI1 → WI2/WI3 consumers. modules/playthrough/hooks/useRunOverview.ts
export type RunOverview = components["schemas"]["CampaignRunOverviewRead"];
export type RunMember = components["schemas"]["CampaignRunMemberRead"];
export function useRunOverview(runId: string): {
  overview: RunOverview | null;  // null while pending, on error, on 404
  isPending: boolean;
  isError: boolean;   // false when notFound is true
  notFound: boolean;  // failure.status === 404
  retry: () => void;
};
// queryKey ["runOverview", runId];
// api.GET("/api/v1/playthrough/runs/{run_id}/overview", { params: { path: { run_id: runId } } })

// WI2 → WI1. modules/playthrough/components/PartySection.tsx
export function PartySection(props: { members: RunMember[] }): ReactElement;

// WI3 → WI2. modules/playthrough/components/InDevelopmentDialog.tsx
export function InDevelopmentDialog(props: { open: boolean; onClose: () => void }): ReactElement;
// no copy props: reads common:inDevelopment.title / .body / .close
```

Translation keys, disjoint per work item in one file
`core/i18n/locales/en/playthrough.json` — WI1 owns `run.*` (`back`, `title`, `notFound`,
`unavailable`, `status.new|inProgress|archived`), WI2 owns `party.*` (`heading`, `ready` with
`{{ready}}`/`{{total}}`, `noCharacter`, `createCharacter`, `role.owner`, `invite.title`,
`invite.subtitle`). WI3 writes `common.json` only.

Status badge mapping (WI1): `setup`,`ready` → `run.status.new`; `active` → `run.status.inProgress`;
`archived`,`finished` → `run.status.archived`.

## Assumptions

- The back link sits at the top of the page, not in the shared header — the design puts it in the
  header bar, but that bar is `core/layout/AppShell` and every other screen shares it; a per-route
  slot is more moving parts than this sprint needs. Blast radius of the alternative: every signed-in
  page.
- A run whose campaign content is gone (`unavailable: true`, so no title to show) renders the same
  plain message as not-found, under its own key — D7's dashboard-side handling is sprint 07's.
- Tests: one `routes/RunRoute.test.tsx` (happy path + either button opening the dialog) plus the
  mandatory `structure.test.ts` pin update; everything else is checked in the browser.

## Open questions

- **Product-visible**: what the run-screen status badge says. The design shows "Run created"; the
  mapping above reuses D3's dashboard words (New / In progress / Archived) so both screens speak one
  language. Confirm or name the wording.
- **Product-visible**: the exact in-development wording. D13 says "along the lines of *Be brave, this
  feature is in development*" — taken literally as the body, with a title and a "Close" button added.
