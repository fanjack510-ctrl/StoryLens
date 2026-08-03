import { defineConfig } from "@playwright/test";

/**
 * WB-2.2 chapter functions Desktop Playwright (CHG-20260803-041).
 * Uses harness route + route mocks — no real provider / formal DB.
 * Dedicated port 1427 (WB-2.1 structure uses 1426).
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: ["**/wb22_chapter_functions.spec.ts"],
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:1427",
    viewport: { width: 1920, height: 1080 },
    channel: "msedge",
  },
  webServer: {
    command: "npm run dev -- --port 1427",
    url: "http://127.0.0.1:1427",
    reuseExistingServer: !process.env.CI,
    env: {
      ...process.env,
      VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
      STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
    },
  },
});
