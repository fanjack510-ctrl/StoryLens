import { defineConfig } from "@playwright/test";

/**
 * CHG-023 final browser acceptance — API/FE started by run_browser_e2e.ps1.
 *
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:1467
 *   CHG023_FIXTURES_JSON=.../acceptance/MANUAL_FIXTURES.json
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "chg023_final_resume_state.spec.ts",
  timeout: 180_000,
  expect: { timeout: 90_000 },
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:1467",
    viewport: { width: 1440, height: 900 },
    channel: "msedge",
    trace: "retain-on-failure",
  },
});
