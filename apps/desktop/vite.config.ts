import { readFileSync, existsSync } from "node:fs";
import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const rootDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(rootDir, "../..");
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

const wholeBookDiagnosticsEnabled = (() => {
  const raw =
    process.env.VITE_WHOLE_BOOK_DIAGNOSTICS_ENABLED ||
    process.env.WHOLE_BOOK_DIAGNOSTICS_ENABLED ||
    "false";
  const value = String(raw).trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
})();

function resolvePublicGitHead(): string {
  if (process.env.VITE_PUBLIC_GIT_HEAD) return String(process.env.VITE_PUBLIC_GIT_HEAD).trim();
  try {
    return execSync("git rev-parse HEAD", { cwd: repoRoot, encoding: "utf8" }).trim();
  } catch {
    return existsSync(resolve(repoRoot, "VERSION")) ? "unknown" : "unknown";
  }
}

export default defineConfig({
  plugins: [react()],
  define: {
    __STORYLENS_APP_VERSION__: JSON.stringify(pkg.version),
    __STORYLENS_PUBLIC_GIT_HEAD__: JSON.stringify(resolvePublicGitHead()),
    // RC builds set VITE_PRO_NATIVE_OVERVIEW_ENABLED=true; repo default remains false.
    __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__: JSON.stringify(nativeOverviewUiEnabled),
    // Wave B diagnostics page — repo default remains false.
    __STORYLENS_WHOLE_BOOK_DIAGNOSTICS_ENABLED__: JSON.stringify(wholeBookDiagnosticsEnabled),
  },
  server: { port: 1420, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: "./src/testSetup.ts",
    exclude: ["e2e/**", "node_modules/**"],
  },
});
