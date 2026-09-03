---
phase: 0
step: "0.4"
title: Frontend scaffold and app shell
summary: Vite + React + TypeScript SPA with MUI theming (system/light/dark), React Router shell, TanStack Query and react-i18next bootstrapped, running as a Compose service — no backend calls yet.
effort: 4
dependencies: ["0.1"]
---

# Step 0.4 — Frontend scaffold and app shell

**Effort: 4** — each piece is boilerplate, but the theme/router/query/i18n shell must be wired coherently. Makes zero API calls, so it runs in parallel with 0.2/0.3; the first live backend call arrives in 0.5.

## Architect's outline

- `frontend/` via `pnpm create vite` (React + TS, SWC); pinned deps: `@mui/material` + `@emotion/*`, `material-symbols`, `react-router` (v7 declarative mode — sufficient for guards + URL state), `@tanstack/react-query` v5, `react-i18next` + `i18next`, `openapi-fetch`; dev deps `openapi-typescript`, `typescript`, `vite` (client deps declared now, wired in 0.5).
- `frontend/src/theme.ts` — MUI theme with `colorSchemes: { light: true, dark: true }`, `defaultMode: "system"`; MUI's built-in localStorage mode persistence covers explicit user overrides.
- `frontend/src/i18n.ts` + `frontend/src/locales/en/translation.json` — react-i18next initialized, English only; app-shell strings are the first keys (no hardcoded UI text).
- `frontend/src/main.tsx` / `App.tsx` — provider stack (ThemeProvider + CssBaseline, QueryClientProvider, I18nextProvider, BrowserRouter); layout shell (MUI AppBar + theme-mode toggle) and an empty home route (the health widget lands in 0.5).
- `docker/frontend.Dockerfile` (dev stage: node + pnpm, Vite dev server) and a `frontend` Compose service (port 5173, bind mount, `VITE_API_URL=http://localhost:8000` set in Compose — not in `.env`). If a real `.env` were ever needed, stop and ask the user; never create one.
- Agent assignment: **frontend-dev**.

## Verification

- `docker compose up`, open `http://localhost:5173`: shell renders; theme toggle cycles system/light/dark and survives reload; `tsc --noEmit` passes.

## Risks / notes

- MUI system-mode `colorSchemes` support requires MUI v6+; pin v6/v7 up front to avoid the legacy dual-theme workaround.
- React Router v7 renamed packages (`react-router`, not `react-router-dom`); fix the import convention now so Phase-1 route guards don't churn.
