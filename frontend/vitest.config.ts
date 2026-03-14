import path from "node:path";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/vitest/**/*.test.ts", "tests/vitest/**/*.test.tsx"],
    setupFiles: ["./tests/vitest/setup.ts"],
  },
});
