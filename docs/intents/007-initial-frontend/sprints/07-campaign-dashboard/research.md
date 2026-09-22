---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 07 — campaign dashboard

## Facts

**The list read.** `GET /api/v1/playthrough/runs` → `CampaignRunSummaryRead[]`, 200 or 401 only
(`frontend/src/api/schema.d.ts:110-118`, `:838-864`). Fields (`schema.d.ts:405-427`): `id`, `campaignId`,
`status`, `createdAt` (ISO date-time), `campaignTitle: string | null`, `campaignSummary: string | null`,
`adventuresCompleted: number`, `adventuresTotal: number | null`, `playerCount: number`, `unavailable: boolean`.
**Ordering is already newest first** — `ORDER BY CampaignRun.id DESC` over creation-ordered ULIDs, archived
included (`backend/app/modules/playthrough/service.py:235-246`, consumed unchanged at `:262-278`). AC1 needs no
client-side sort and **no backend work**.

**`unavailable: true`** means the run's pinned campaign content (`campaign_id` + `content_version`) no longer
loads; title, summary and `adventuresTotal` come back `null`, while `adventuresCompleted` and `playerCount` are
still real, because they are counted off the run's own rows (`service.py:249-259`, `:299-321`;
`schema.d.ts:396-404`).

**Status vocabulary.** `setup` → New, `ready`/`active` → In progress, `archived`/`finished` → Archived, unknown →
New, keyed `playthrough:run.status.*` — `frontend/src/modules/playthrough/routes/RunRoute.tsx:32-44`.

**The screen being replaced.** `HomeRoute` (`/`, greeting `home:greeting`, h1 with `tabIndex={-1}` focused on
mount) and the placeholder `DashboardRoute` (`/dashboard`, heading only) live in `frontend/src/modules/home/`;
both are registered in `frontend/src/App.tsx:14-15,30-31`. Their copy is `core/i18n/locales/en/home.json`,
registered `core/i18n/index.ts:8,12` and pinned `structure.test.ts:164`.

**Suite-wide fallout.** Six suites render or land on `/` and assert `"Welcome, thorin."`
(`App.test.tsx:67`, `modules/auth/components/RequireAnonymous.test.tsx:40`, `modules/auth/routes/SignUpRoute.test.tsx:134`,
`modules/auth/routes/SignInRoute.test.tsx:212-226` — which also pins *focus* on that h1 —, plus
`accountMenu.test.tsx:26`, `modules/auth/csrf.test.tsx:25,45`, `productName.test.tsx:46`,
`modules/home/routes/HomeRoute.test.tsx`, which carries the whole `RequireAuth`-on-`/` coverage). Two acceptance
tests deep-link `/dashboard` as "a second protected address" (`returnToRequestedPage.test.tsx:43`,
`signOutForgetsRememberedAddress.test.tsx:58`); `/runs/:runId` already serves that role through the real guard
(`modules/playthrough/routes/RunRoute.test.tsx:38-45`), so `/dashboard` can go.

**Greeting name.** `useCurrentUser().user.username` — the only name the product has
(`modules/auth/hooks/useCurrentUser.ts:35-46`).

**Relative dates.** `Intl.RelativeTimeFormat` is a platform builtin; verified in this project's own container
(node v24.21.0, `docker compose run node-cli`): `new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(-1, "day")`
→ `"yesterday"`, `format(-3, "week")` → `"3 weeks ago"`. Approach: `seconds = (Date.parse(createdAt) - Date.now())/1000`
(negative for the past), walk `year 31536000 · month 2592000 · week 604800 · day 86400 · hour 3600 · minute 60`,
take the first unit whose size ≤ `|seconds|`, else `"second"`; locale = `useTranslation().i18n.language`. No
library, no new dependency.

**Guard rails.** `structure.test.ts:152-215` pins `core/`'s file list exactly; `:117-149` bans hex/`rgb()`/`hsl()`
in `.ts/.tsx/.json` and in any `.css` outside `core/theme/tokens/`; `:264-300` pins `home → auth:useCurrentUser`
as the one cross-module import. `InDevelopmentDialog` deliberately takes no copy props
(`modules/playthrough/components/InDevelopmentDialog.tsx:1-10`), so AC4 needs its own dialog. Card styling
precedent: `modules/playthrough/components/PlayerCard.tsx:33-40`; page width 1080 comes from `core/layout/AppShell.tsx`.

**Module call.** The dashboard belongs in `modules/playthrough`: it reads playthrough's endpoint, links into
playthrough's run screen and shares its status vocabulary. Keeping it in `home` would either duplicate that
mapping or make `home` import playthrough internals. `modules/home` is therefore deleted whole — the AC6 list:
`modules/home/` (both routes, both tests, `README.md`), `core/i18n/locales/en/home.json` and its import/registration
(`core/i18n/index.ts:8,12`), the `home.json` pin (`structure.test.ts:164`), criterion 42(c) retargeted from `home`
to `playthrough` (`structure.test.ts:264-300`), the `/dashboard` route, and `docs/architecture.md:28`'s module list.
`HomeRoute.test.tsx`'s guard coverage is *moved*, not dropped.

## Work items

- **WI1 — the dashboard screen** (`modules/playthrough`): `useRunSummaries` hook, `DashboardRoute` (greeting +
  subtitle, section label, run cards, CTA card, empty state, unavailable dialog), `RunCard`, `runStatus.ts`
  extracted from `RunRoute.tsx:32-44` and reused by both screens, relative-date helper, the `dashboard.*` subtree in
  `core/i18n/locales/en/playthrough.json`, own tests, module `README.md`.
- **WI2 — retire the landing page**: `App.tsx` route table (`/` → `DashboardRoute`, `/dashboard` and `HomeRoute`
  gone), delete `modules/home` and `home.json`, update `core/i18n/index.ts` and `structure.test.ts`, move
  `HomeRoute.test.tsx`'s guard coverage onto `/`, retarget the two `/dashboard` acceptance tests to `/runs/abc`,
  add the runs stub to every suite that renders `/`, update `docs/architecture.md:28`.

## Interfaces

```ts
// frontend/src/modules/playthrough/routes/DashboardRoute.tsx  (WI1 → WI2 imports it)
export function DashboardRoute(): ReactElement;   // no props; App.tsx renders it at "/"

// frontend/src/modules/playthrough/hooks/useRunSummaries.ts   (WI1)
export type RunSummary = components["schemas"]["CampaignRunSummaryRead"];
export function useRunSummaries(): {
  runs: RunSummary[];        // [] until loaded; server order kept, never re-sorted
  isPending: boolean; isError: boolean; retry: () => void;
};                           // queryKey ["runSummaries"], unwrap() like useRunOverview.ts

// frontend/src/modules/playthrough/runStatus.ts               (WI1; RunRoute.tsx switches to it)
export type RunStatusKey = "run.status.new" | "run.status.inProgress" | "run.status.archived";
export function runStatusKey(status: string): RunStatusKey;          // mapping of RunRoute.tsx:34-44, unchanged
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume";
// "begin" for status "setup" only, "resume" for everything else (brief assumption: finished runs
// keep a button until sprint 08 sorts them under Archived). Stays in the module — core/ only on a second caller.
```

Contract WI2 relies on: the greeting is the page's single `<h1>`, `tabIndex={-1}`, focused on mount, rendered from
`dashboard.greeting` with `{{username}}` **independently of the run-list query state** — so
`SignInRoute.test.tsx:212-226`'s focus pin and every guard suite keep passing with only the copy changed. Every
suite that renders `/` must stub `GET /api/v1/playthrough/runs` (`mockRoute("GET", "/api/v1/playthrough/runs", { status: 200, body: [] })`).

AC4: an unavailable card renders muted, no Begin/Resume, the whole card activatable (MUI `CardActionArea`, no
`to`), opening a dashboard-owned MUI `Dialog` with its own `dashboard.unavailable.*` copy — never
`InDevelopmentDialog`'s.

## Open questions

- *product-visible*: with no runs, does the greeting keep a subtitle, or does the invitation copy carry it alone?
  Agent's call for veto: greeting stays, subtitle is dropped, the invitation card speaks (AC3, AC5).
- *product-visible*: the meta line reads "Adventure n of m" with n = the adventure the party is **on**
  (`min(adventuresCompleted + 1, adventuresTotal)`), so a fresh run reads "Adventure 1 of 8", not "0 of 8".
  Agent's call for veto.
- *technical*: none open — no backend change is needed for any criterion.
