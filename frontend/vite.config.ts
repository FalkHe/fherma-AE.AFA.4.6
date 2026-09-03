import react from "@vitejs/plugin-react-swc";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on 0.0.0.0: inside the Compose container the dev server must
    // accept connections from outside the container, or the port mapping is
    // useless.
    host: true,
    port: 5173,
    // Fail loudly instead of silently moving to 5174, which the Compose port
    // mapping would not follow.
    strictPort: true,
    watch: {
      // Bind mounts do not always propagate inotify events into the container
      // (notably Docker Desktop on WSL2). The Compose service opts into
      // polling; local runs keep the cheaper native watcher.
      usePolling: process.env.VITE_SERVER_USE_POLLING === "true",
    },
  },
});
