# Frontend image: Vite dev server.
# Build context is the repository root.
#
# Development only. Production serves the compiled SPA from the backend image
# (see docs/architecture.md), so a build stage is added there, not here.
FROM node:24-bookworm-slim AS dev

# Pinned to the `packageManager` field in frontend/package.json. Installed with
# npm rather than corepack, which is deprecated in the Node distribution.
ARG PNPM_VERSION=11.17.0
RUN npm install --global "pnpm@${PNPM_VERSION}"

WORKDIR /app

# Dependencies first: this layer is cached until the manifests change.
# pnpm-workspace.yaml carries the install settings (allowed build scripts).
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

EXPOSE 5173

# vite.config.ts binds 0.0.0.0 so the published port reaches the server.
CMD ["pnpm", "run", "dev"]
