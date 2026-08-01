import { defineConfig } from "@playwright/test";

/**
 * WB-2.1 structure stages Desktop Playwright (CHG-20260801-035).
 * Uses route mocks + Free product flag — no real provider / formal DB.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: ["**/wb21_structure_stages.spec.ts"],
  timeout: 90_000,
  use: {
    baseURL: "http://127.0.0.1:1426",
    viewport: { width: 1920, height: 1080 },
    channel: "msedge",
  },
  webServer: {
    command: "npm run dev -- --port 1426",
    url: "http://127.0.0.1:1426",
    reuseExistingServer: !process.env.CI,
    env: {
      ...process.env,
      VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
      STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
    },
  },
});
