import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://127.0.0.1:1421",
    viewport: { width: 1440, height: 900 },
    channel: "msedge",
  },
  webServer: {
    command: "npm run dev -- --port 1421",
    url: "http://127.0.0.1:1421",
    reuseExistingServer: true,
  },
});
