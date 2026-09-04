# Frontend — Motorcycle Buying Advisor

React + TypeScript SPA built with Vite (`@vitejs/plugin-react-swc`). See the
root [`README.md`](../README.md) for prerequisites and full-stack setup
(Docker Compose, `.env`), and `docs/general/frontend-stack.md` plus the Frontend
Architecture section of `docs/general/architecture.md` for the binding conventions.

## Scripts

| Command              | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| `pnpm dev`           | Vite dev server on `http://localhost:5173`              |
| `pnpm build`         | Type-check (`tsc -b`) and produce `dist/`               |
| `pnpm typecheck`     | Type-check only                                         |
| `pnpm test`          | Vitest one-shot run (jsdom, Testing Library; network is stubbed — no backend needed) |
| `pnpm test:watch`    | Vitest watch mode                                       |
| `pnpm lint`          | ESLint                                                  |
| `pnpm preview`       | Serve the production build locally                      |
| `pnpm generate:api`  | Regenerate `src/api/schema.d.ts` from the running backend's OpenAPI schema (stack must be up; see `.claude/skills/qa-checklist/SKILL.md`) |

## Conventions

- **Server state** lives in TanStack Query only; URL state in React Router
  (v7 declarative mode — import from `react-router`, never
  `react-router-dom`).
- **API access** goes through the generated `openapi-fetch` client (added in
  step 0.5); no hand-written request types.
- **Strings** are i18n keys in `src/locales/<lng>/translation.json`. The
  catalogue also types the keys, so `t("typo.key")` is a compile error.
- **Theme** modes are `system | light | dark`, default `system`; MUI persists
  an explicit override under the `mui-mode` localStorage key.
- **Icons** are Material Symbols glyphs: `<Icon>dark_mode</Icon>`.

## Configuration

`VITE_API_URL` points at the backend and is supplied by the `frontend` Compose
service (see `compose.yaml`). There is no `frontend/.env`.
