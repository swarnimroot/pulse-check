import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// `base: "./"` makes built asset URLs relative ("./assets/foo.js") so the
// app works regardless of the URL prefix it's served from. Combined with a
// HashRouter on the React side, the project is fully prefix-agnostic — a
// reverse-proxy rename (e.g. /pulse-check → /something-else) doesn't require
// a rebuild.
export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    globals: false,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
