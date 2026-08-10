#!/usr/bin/env node
/**
 * CHG-078 — capture formal Whole-Book V2 module screenshots via Playwright.
 * Usage: node apps/desktop/scripts/chg078-formal-screenshots.mjs
 */
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(__dirname, "..");

const result = spawnSync(
  "npx",
  [
    "playwright",
    "test",
    "e2e/chg078-formal-whole-book-v2-screenshots.spec.ts",
    "--config=playwright.config.ts",
  ],
  {
    cwd: desktopRoot,
    stdio: "inherit",
    shell: true,
    env: {
      ...process.env,
      VITE_WHOLE_BOOK_FREE_PRODUCT_ENABLED: "true",
    },
  },
);

process.exit(result.status ?? 1);
