import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    globals: false,
    css: true,
    // Important: Playwright e2e specs live under /e2e and should NOT be picked up by vitest.
    exclude: ["e2e/**", "**/node_modules/**", "**/.next/**"],
  },
});


