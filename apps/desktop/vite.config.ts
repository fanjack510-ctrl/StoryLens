import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const rootDir = dirname(fileURLToPath(import.meta.url));
const pkg = JSON.parse(readFileSync(resolve(rootDir, "package.json"), "utf-8")) as {
  version: string;
};

const nativeOverviewUiEnabled = (() => {
  const raw =
    process.env.VITE_PRO_NATIVE_OVERVIEW_ENABLED ||
    process.env.PRO_NATIVE_OVERVIEW_ENABLED ||
    "false";
  const value = String(raw).trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
})();

export default defineConfig({
  plugins: [react()],
  define: {
    __STORYLENS_APP_VERSION__: JSON.stringify(pkg.version),
    // RC builds set VITE_PRO_NATIVE_OVERVIEW_ENABLED=true; repo default remains false.
    __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__: JSON.stringify(nativeOverviewUiEnabled),
  },
  server: { port: 1420, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: "./src/testSetup.ts",
    exclude: ["e2e/**", "node_modules/**"],
  },
});
