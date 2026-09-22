---
author: fhit:architect
owner: agent
created: 2026-09-22
---
# Research: sprint 007/08 — dashboard tags

## Facts

- Run status vocabulary is `setup|ready|active|archived|finished`
  (`backend/app/modules/playthrough/models.py:40`), sent through as a plain string on the list read
  (`CampaignRunSummaryRead.status`, `backend/app/modules/playthrough/schemas.py:38`,
  `backend/app/modules/playthrough/service.py:310`). `frontend/src/api/schema.d.ts:411` types it `string`,
  not a union. The list already includes archived runs and is newest-first
  (`service.py:260-266`) — no query parameter, no server-side filter. **No backend work in this sprint.**
- Transitions today: `setup` on creation (`models.py:48`); `ready` once a character exists
  (`service.py:532`); `active` only via `activate_campaign_run`, which no route calls yet
  (`service.py:580-583`); `finished` when the last adventure completes (`service.py:1364`);
  `archived` via archive, which *deletes* a `setup` run instead of archiving it (`service.py:567-575`).
- `frontend/src/modules/playthrough/runStatus.ts:8-19` — `runStatusKey` already folds the five statuses
  onto the three badge words: `setup`/unknown → `run.status.new`, `ready`+`active` → `run.status.inProgress`,
  `archived`+`finished` → `run.status.archived`. It is the badge on both the dashboard card
  (`components/CampaignCard.tsx:135`) and the run screen (`routes/RunRoute.tsx:72`). The three tag labels
  D3 names are word-for-word those three badge words, so the tag set *is* `RunStatusKey`
  and needs no second mapping and no new label keys (`core/i18n/locales/en/playthrough.json:5-9`).
- `runStatus.ts:25-26` — `runActionKey` returns `resume` for everything that is not "New", i.e. also for
  `archived` and `finished`. `CampaignCard.tsx:156-163` therefore renders a "Resume" link on an archived
  card, which AC3 forbids. `runActionKey` has exactly one caller (`CampaignCard.tsx:120`).
- `CampaignCard.tsx:107-167` renders art placeholder, title, badge, teaser, meta line and the action; the
  action `<Button component={RouterLink}>` is the card's *only* navigation, so dropping it satisfies
  "cannot be opened". The existing muted variant (`UnavailableCard`, `CampaignCard.tsx:55-105`,
  `opacity: 0.6`, `backgroundColor: var(--surface-inset)`) drops title, teaser and meta entirely and adds a
  "why" trigger — wrong shape for archived, which keeps all its copy (design line 154/161-162: tone
  `sunken`, opacity .72). Reuse the muting values, not the component.
- `routes/DashboardRoute.tsx:43-83` — `hasRuns = runs.length > 0` gates the invitation (`CampaignCta prominent`)
  against list + footer CTA; the subtitle counts `runs.length`. Greeting renders independently of the query
  and is the focus target (`DashboardRoute.tsx:39-49`) — untouched.
- Nothing under `frontend/src` persists UI state: no storage, cookie, URL-param or query-persist call
  (`core/api/client.ts:3` keeps even the CSRF token in memory). `structure.test.ts:144-152` (UI-40) already
  fails the suite on any `localStorage`/`sessionStorage`/`document.cookie` reference, so AC5 is enforced by
  an existing test. Nothing else in `structure.test.ts` is touched: `core/` file pin (`:154-206`) is unchanged
  (the one i18n file already exists) and the `playthrough → auth` edge (`:266-318`) stays as-is.
- Design: tag row is one section — eyebrow "MY CAMPAIGNS" left, three `Tag` pills right
  (`Dashboard.dc.html:44-50`); selected pill = accent fill + lantern text + amber border
  (`_ds_bundle.js:736-765`); archived note sits *after* the cards (`:78-79`).
- MUI 9.4.0 (`frontend/pnpm-lock.yaml:395`). `ToggleButtonGroup exclusive` gives `role="group"` +
  `aria-pressed` per button and emits `null` when the selected button is clicked again — guard with
  `if (next !== null)` (MUI 9.2 docs, "Enforce value set" — context7).
- Tests: `routes/DashboardRoute.test.tsx` (vitest, no globals; `renderApp`/`mockRoute` from `src/test/`).
  Its AC1/AC2 case (`:69-102`) renders an `active` and a `setup` run together and asserts both cards — with
  filtering on, those two no longer show at once; that case must be split per tag.

## Status → tag

| status | tag | why |
|---|---|---|
| `setup`, unknown | New | `runStatusKey` default |
| `ready` | In progress | keeps badge and tag identical — see open question |
| `active` | In progress | AC2's "adventure was entered" |
| `archived` | Archived | AC2 |
| `finished` | Archived | brief assumption ← D11 agent's call |

## Work items

- WI1 dashboard tags (frontend, one item): tag row, client-side filter, archived card variant, archived note,
  empty-tag line, plus the `runActionKey` fix and the i18n keys — one route, one component, one helper, one
  test file, all in `modules/playthrough`.

## Interfaces

Single work item, so these are internal contracts to hold, not hand-offs.

```ts
// runStatus.ts — tag identity is the existing RunStatusKey; no new mapping function.
export function runActionKey(status: string): "dashboard.card.begin" | "dashboard.card.resume" | null;
//   → null exactly when runStatusKey(status) === "run.status.archived"  (AC3)

// DashboardRoute.tsx — AC4/AC5
const TAGS: RunStatusKey[] = ["run.status.inProgress", "run.status.new", "run.status.archived"];
const [picked, setPicked] = useState<RunStatusKey | null>(null);   // component state only, never persisted
const defaultTag: RunStatusKey = runs.some((r) => runStatusKey(r.status) === "run.status.inProgress")
  ? "run.status.inProgress"
  : "run.status.new";
const activeTag = picked ?? defaultTag;                            // derived, no effect, no flicker
const visible = runs.filter((r) => runStatusKey(r.status) === activeTag);
// tags + note + list render only when runs.length > 0; otherwise <CampaignCta prominent /> alone (AC4).
```

New keys, `dashboard.tags.*` (this sprint owns that subtree; tag labels reuse `run.status.*`):
`heading` ("My campaigns"), `groupLabel` (group `aria-label`), `empty` (no runs under this tag),
`archivedNote` (kept, read-only, no unarchive — AC3).

## Assumptions

- Tag order follows the design: In progress · New · Archived.
- Archived note renders *above* the archived list (the Outcome says runs sit "under a note"); the design
  places it after the cards.
- The subtitle keeps counting all runs, not the filtered ones — it greets the shelf, not the tag.
- An archived run is still reachable by typing its address; AC3 is about the card (matches D7's unavailable card).

## Open questions

- **Product-visible, non-blocking:** a run whose players have made characters but which has entered no
  adventure (`ready`) shows the badge "In progress" today. It therefore lands under "In progress", not "New",
  which reads against D11's literal "New = not yet started". Splitting them would make a card under "New"
  carry an "In progress" badge, or force a badge change on the run screen (sprint 05, out of scope). Proceeding
  with badge and tag identical; the state is not reachable from the product today (character creation is the
  in-development dialog, D4), so nothing a player can do exposes it.
