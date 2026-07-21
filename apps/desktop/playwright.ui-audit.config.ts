import { defineConfig } from "@playwright/test";

/**
 * StoryLens UI Audit screenshot runner.
 * Viewport / locale / timezone match the audit brief.
 */
export default defineConfig({
  testDir: "./e2e/ui-audit",
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["json", { outputFile: "../../../artifacts/ui-audit-work/playwright-report.json" }]],
  use: {
    baseURL: "http://127.0.0.1:1421",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    colorScheme: "light",
    channel: "msedge",
    trace: "off",
    video: "off",
    screenshot: "off",
  },
  webServer: {
    command: "npm run dev -- --port 1421",
    url: "http://127.0.0.1:1421",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
