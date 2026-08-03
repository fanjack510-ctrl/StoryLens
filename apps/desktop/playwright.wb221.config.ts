import { defineConfig } from "@playwright/test";

/**
 * WB-2.2.1 / CHG-20260803-047 Desktop E2E stabilization.
 * Route mocks + Free product flag — no real provider / formal DB.
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: ["**/wb221_e2e_stabilization.spec.ts"],
  timeout: 120_000,
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
      VITE_WHOLE_BOOK_FIXTURE_PREVIEW_ENABLED: "true",
      STORYLENS_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
    },
  },
});
