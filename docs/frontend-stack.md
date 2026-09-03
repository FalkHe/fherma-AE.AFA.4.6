# Frontend Stack — Motorcycle Buying Advisor
 
**Fixed constraints:** React · cookie auth + CSRF · SSE progress · resumable
consultations · admin backlog review · catalogue images · cited sources shown.
 
---
 
## Stack
 
```
React + TypeScript + Vite
│
├── UI
│   ├── Material UI
│   │   ├── Material Design 2
│   │   ├── responsive: desktop-first, mobile-capable
│   │   └── theme: system | light | dark   (default: system)
│   ├── Material Symbols
│   └── images: srcset + loading="lazy"
│
├── Routing
│   └── React Router
│       ├── user/admin guards
│       └── URL search/filter state
│
├── Server state
│   └── TanStack Query
│
├── API
│   ├── openapi-typescript
│   ├── openapi-fetch
│   └── middleware: CSRF header + credentials
│
├── Realtime
│   └── EventSource (native) → query invalidation
│
├── Content rendering
│   ├── react-markdown
│   └── remark-gfm
│
├── i18n
│   └── react-i18next             (English-only catalogue initially)
│
├── Forms
│   ├── React Hook Form            (optional)
│   └── Zod + @hookform/resolvers  (optional, with the above)
│
└── pnpm
```
 
---
 
## Justification
 
| Component | Why |
|---|---|
| React + TypeScript | Mandated frontend; types pair with generated API client |
| Vite | Dev server and build; no configuration to speak of |
| Material UI | Forms, tables, dialogs for chat, comparison, and admin screens |
| Material Design 2 | Settled; no reason to chase MD3 |
| Desktop-first | Spec comparison is the view that resists narrow viewports |
| Theme colorSchemes | System/light/dark is a config block in MUI, not work |
| Material Symbols | Icon set, one dependency |
| React Router | Consultation list, consultation detail, model detail, admin backlog |
| Route guards | Backlog approval is admin-only |
| URL search state | Catalogue filters survive reload and are shareable |
| TanStack Query | Caches consultations and catalogue across navigation; invalidation is the SSE target |
| openapi-typescript | FastAPI emits the schema; frontend types derive from it rather than duplicating it |
| openapi-fetch | Typed calls against that schema, no client hand-maintenance |
| API middleware | Attaches CSRF header and credentials once, not per call |
| EventSource | Native SSE; sends the session cookie and reconnects unaided |
| react-markdown | Assistant replies are markdown; raw HTML off by default keeps retrieved prose non-executable |
| remark-gfm | Tables and strikethrough in model output |
| react-i18next | Strings externalized from day one; adding a locale later is translation work, not refactoring |
| React Hook Form | Only if forms grow past login, registration, and approval |
| Zod | Client-side form validation; pointless without a form library, since the backend validates and OpenAPI supplies types |
| pnpm | Faster installs, strict node_modules |
 
## Excluded
 
| Component | Why |
|---|---|
| Redux / Zustand | TanStack Query holds server state; the remainder is component state |
| fetch-event-source | Solves SSE with auth headers; cookie auth makes native EventSource sufficient |
| Chart library | Spec comparison reads better as a table; add MUI X Charts only if a visual comparison is wanted |
| List virtualization | 150 models is not a virtualization problem |
| Zod response parsing | Would re-validate a trusted backend against types already generated from its schema |
