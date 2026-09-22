import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const allowedHost = process.env.VITE_ALLOWED_HOST?.trim();
const apiProxyTarget = process.env.VITE_API_PROXY_TARGET?.trim();

// Plain object, not a function: vitest.config.ts merges this with
// `mergeConfig` (step-0.1.md §6.2).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    // Vite permits localhost and IP addresses by default. A reverse proxy's
    // hostname must be opted into explicitly to avoid DNS-rebinding attacks.
    allowedHosts: allowedHost ? [allowedHost] : [],
    proxy: apiProxyTarget
      ? {
          "/api": {
            target: apiProxyTarget,
            changeOrigin: true,
          },
        }
      : undefined,
    watch: {
      // Bind mounts do not propagate inotify events reliably; compose.yaml
      // sets VITE_SERVER_USE_POLLING=true.
      usePolling: process.env.VITE_SERVER_USE_POLLING === "true",
    },
  },
});
