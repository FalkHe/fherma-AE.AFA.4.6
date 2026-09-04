# Frontend stack

**Fixed constraints:** React · cookie auth + CSRF · SSE progress · resumable
consultations · admin backlog review · catalogue images · cited sources shown.

Exact versions live in `frontend/package.json`.

## Stack

```text
React 19 + TypeScript + Vite
│
├── UI
│   ├── Material UI (Material Design 2)
│   │   ├── responsive: desktop-first, mobile-capable
│   │   └── theme: system | light | dark   (default system, persisted as "mui-mode")
│   └── Material Symbols                  (ligatures via <Icon>)
│
├── Routing
│   └── react-router v7                   (declarative mode)
│       ├── RequireAuth / RequireAdmin
│       └── URL search/filter state
│
├── Server state
│   └── TanStack Query
│
├── API
│   ├── openapi-typescript                (schema.d.ts, committed)
│   ├── openapi-fetch
│   └── middleware: CSRF header + credentials + 401 handling
│
├── Realtime
│   └── EventSource (native) → query invalidation
│
├── Content rendering
│   ├── react-markdown + remark-gfm
│   └── UntrustedMarkdown                 (the only renderer; raw HTML off)
│
├── Forms
│   └── React Hook Form + Zod + @hookform/resolvers
│
├── i18n
│   └── react-i18next                     (English only, keys compile-checked)
│
├── Errors
│   └── AppErrorBoundary                  (render crashes only)
│
├── Testing
│   └── Vitest + Testing Library + jsdom
│
└── pnpm
```

## Justification

| Component | Why |
|---|---|
| React + TypeScript | Mandated frontend; types pair with the generated API client |
| Vite | Dev server and build; no configuration to speak of |
| Material UI | Forms, tables, dialogs for chat, comparison and admin screens |
| Material Design 2 | Settled; no reason to chase MD3 |
| Desktop-first | Spec comparison is the view that resists narrow viewports |
| Theme colorSchemes | System/light/dark is a config block in MUI, not work |
| Material Symbols | One dependency, one ligature font — `@mui/icons-material` is deliberately absent |
| react-router | Consultations, catalogue, model detail, admin backlog and review |
| Route guards | Admin surfaces are admin-only in the UI; the backend dependency is the real boundary |
| URL search state | Catalogue filters survive reload and are shareable |
| TanStack Query | Caches consultations and catalogue across navigation; invalidation is the SSE target |
| openapi-typescript | FastAPI emits the schema; frontend types derive from it rather than duplicating it |
| openapi-fetch | Typed calls against that schema, no hand-maintained client |
| API middleware | Attaches the CSRF header and credentials once, and clears the cached user on any non-auth 401 |
| EventSource | Native SSE; sends the session cookie and reconnects unaided |
| react-markdown + remark-gfm | Assistant replies, retrieved prose and Wikipedia articles are Markdown with tables |
| UntrustedMarkdown | One wrapper for all three sites: GFM only, raw HTML off, `rehype-raw` never added, links forced to `target=_blank rel="noopener noreferrer"` |
| React Hook Form + Zod | The admin draft-spec and identity forms are large (spec fields, type-code chips, a trims field array); submit-only validation with typed resolvers. Catalogue and chat screens deliberately use neither |
| react-i18next | Strings externalized from day one; adding a locale is translation work, not refactoring |
| AppErrorBoundary | One root boundary turns a render crash into a reload prompt; query errors are handled per screen |
| Vitest | Shares the Vite config; jsdom, no globals |
| pnpm | Faster installs, strict `node_modules` |

## Excluded

| Component | Why |
|---|---|
| Redux / Zustand | TanStack Query holds server state; the remainder is component state |
| fetch-event-source | Solves SSE with auth headers; cookie auth makes native EventSource sufficient |
| `rehype-raw` | Would re-enable raw HTML in untrusted Markdown — the whole point of the wrapper |
| Chart library | Spec comparison reads better as a table; add MUI X Charts only if a visual comparison is wanted |
| List virtualization | A few hundred models is not a virtualization problem |
| Zod response parsing | Would re-validate a trusted backend against types already generated from its schema |
| Snackbar/toast infrastructure | Errors surface per screen as an `EmptyState` with refetch; the one exception is the admin backlog transition failure |

## Conventions

- **Server state is never copied into component state.** Envelope unwrapping
  happens only in hooks; query keys are centralised in `src/queryKeys.ts`.
- **`react-router`, never `react-router-dom`.**
- **One optimistic update in the whole app**: the outgoing chat message.
- List hooks walk pages (`page[size]=100`) until `meta.totalCount` is reached;
  the catalogue is the exception at `PAGE_SIZE = 24`.
- No polling. `EventSource` reconnects on its own; a reconnect triggers a
  blanket invalidation.
- Operation `message`/`error` text is rendered verbatim — the deliberate i18n
  exemption.
- Tests stub `fetch` through `src/test/network.ts`; the setup file installs one
  dispatcher before app modules load because openapi-fetch captures `fetch` at
  import time. Unstubbed requests throw.
