/**
 * CHG-078 formal Whole-Book V2 screenshots — Playwright with API route mocks.
 * Run: npx playwright test e2e/chg078-formal-whole-book-v2-screenshots.spec.ts
 */
import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../..");
const OUT_DIR = path.join(
  REPO_ROOT,
  "release/evidence/whole-book/CHG-20260810-078/screenshots",
);
const FIXTURE_PATH = path.join(
  REPO_ROOT,
  "apps/desktop/src/features/wholeBookV2/fixtures/analysisV2.json",
);

const MODULES = [
  { key: "overview", file: "01-overview.png", label: "全书总览" },
  { key: "story", file: "02-story.png", label: "故事" },
  { key: "characters", file: "03-characters.png", label: "人物" },
  { key: "suspense", file: "04-suspense.png", label: "悬念" },
  { key: "pacing", file: "05-pacing.png", label: "节奏" },
  { key: "chapters", file: "06-chapters.png", label: "章节" },
  { key: "assessment", file: "07-assessment.png", label: "综合诊断" },
] as const;

test.describe("CHG-078 formal whole-book V2 screenshots", () => {
  test.beforeAll(() => {
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(OUT_DIR, "..", "ROUTE.txt"),
      "/books/42/whole-book\n",
      "utf8",
    );
  });

  test("captures seven module screenshots with mocked APIs", async ({ page }) => {
    const fixture = JSON.parse(fs.readFileSync(FIXTURE_PATH, "utf8"));

    await page.route("**/api/v1/settings/active-cloud-provider**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ provider_name: "deepseek", model_name: "deepseek-chat" }),
      });
    });

    await page.route("**/api/v1/books/42/whole-book/prepare**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          book_id: 42,
          book_title: fixture.book_metadata.title,
          chapter_count: fixture.book_metadata.chapter_count,
          character_count: fixture.book_metadata.character_count,
          mode: "free",
          mode_label: "原生全书分析",
          product_enabled: true,
          real_provider_enabled: true,
          run_creation_enabled: true,
          provider_available: true,
          fixture_preview_enabled: false,
          latest_run: {
            run_id: 7801,
            book_id: 42,
            status: "completed",
            mode: "free",
            result_origin: "formal",
            engine_id: "whole_book_v2_hierarchical",
            snapshot_id: fixture.book_metadata.snapshot_id,
            started_at: "2026-08-10T00:00:00Z",
            completed_at: "2026-08-10T01:00:00Z",
          },
          recoverable_run: null,
          snapshot_rebuild_required: false,
          estimate: null,
          recommended_limits: {
            max_provider_calls: 100,
            max_input_tokens: 100000,
            max_output_tokens: 50000,
            max_cost_budget_cny: "10.00",
          },
          blocking_reasons: [],
          warnings: [],
        }),
      });
    });

    await page.route("**/api/v1/whole-book-runs/7801/v2**", async (route) => {
      if (route.request().url().includes("/progress")) {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });

    await page.goto("/books/42/whole-book");
    await expect(page.getByTestId("whole-book-v2-report")).toBeVisible({ timeout: 15000 });

    for (const mod of MODULES) {
      await page
        .getByRole("navigation", { name: "全书分析模块" })
        .getByRole("button", { name: new RegExp(mod.label) })
        .click();
      await expect(page.getByTestId("whole-book-v2-report")).toHaveAttribute(
        "data-module",
        mod.key,
      );
      await page.screenshot({
        path: path.join(OUT_DIR, mod.file),
        fullPage: true,
      });
    }
  });
});
