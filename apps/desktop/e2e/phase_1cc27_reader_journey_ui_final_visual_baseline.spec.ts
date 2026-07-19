import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SCREENSHOT_DIR = resolve(
  __dirname,
  "../../../audits/mvp-functional-baseline-v1/reader-journey-ui-final-v2.7/screenshots",
);

test.describe("Reader Journey UI Final Freeze v2.7 visual baseline", () => {
  async function mockApis(page: import("@playwright/test").Page) {
    const visualization = buildVisualizationFixture();
    const scenes = buildScenes();
    const paragraphs = buildChapterParagraphs();
    let createRun = 0;
    let createJourney = 0;

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok", database: "ok", default_provider: "fake" } });
      }
      if (url.match(/\/books\/1$/) && method === "GET") {
        return route.fulfill({
          json: {
            id: 1,
            title: "Fixture Novel",
            source_file_name: "fixture.txt",
            source_file_hash: "deadbeef",
            created_at: "2026-01-01T00:00:00Z",
          },
        });
      }
      if (url.includes("/chapters") && !url.includes("paragraphs") && !url.includes("analysis-runs")) {
        return route.fulfill({
          json: [
            {
              id: 2,
              book_id: 1,
              chapter_index: 1,
              section_type: "chapter",
              title: "第一章",
              display_title: "第1章 戏鬼回家",
            },
          ],
        });
      }
      if (url.includes("/chapters/") && url.includes("/paragraphs")) {
        return route.fulfill({
          json: {
            items: paragraphs,
            offset: 0,
            limit: 500,
            total: paragraphs.length,
            has_more: false,
          },
        });
      }
      if (url.match(/\/analysis-runs\/55$/) && method === "GET") {
        return route.fulfill({
          json: {
            id: 55,
            subject_id: "2",
            provider: "fake",
            model: "fake",
            status: "succeeded",
            progress_current: 14,
            progress_total: 14,
            execution_mode: "local",
            cloud_consent: false,
            sends_content_to_cloud: false,
            retryable: false,
            created_at: "2026-01-01T00:00:00Z",
            completed_at: "2026-01-01T00:05:00Z",
            reusable_checkpoint_count: 0,
            conflicted_checkpoint_count: 0,
            checkpoint_total_count: 0,
            checkpoint_available: false,
            completed_scene_count: 14,
            total_scene_count: 14,
          },
        });
      }
      if (url.includes("/analysis-runs/55/reader-journey") && method === "POST") {
        createJourney += 1;
        return route.fulfill({ status: 202, json: { journey_run_id: 99 } });
      }
      if (url.includes("/analysis-runs/55/reader-journey")) {
        return route.fulfill({
          json: {
            status: "succeeded",
            journey_run_id: 2,
            visualization,
            scene_profiles: [],
            chapter_summary: visualization.chapter_summary,
          },
        });
      }
      if (url.includes("/analysis-runs/55/results")) {
        return route.fulfill({
          json: {
            run: {
              id: 55,
              status: "succeeded",
              provider: "fake",
              model: "fake",
              created_at: "2026-01-01T00:00:00Z",
            },
            chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第1章 戏鬼回家" },
            boundary_revision: null,
            summary: { total_scene_count: 14 },
            scenes,
          },
        });
      }
      if (url.match(/\/chapters\/\d+\/analysis-runs$/) && method === "POST") {
        createRun += 1;
        return route.fulfill({ status: 202, json: { run_id: 999 } });
      }
      if (url.match(/\/scenes\/\d+\/paragraphs/)) {
        return route.fulfill({
          json: {
            paragraphs: [
              {
                id: "B0001-C0002-P0090",
                raw_text: "第九景。",
                in_scene: true,
                paragraph_index: 90,
              },
            ],
          },
        });
      }
      if (url.includes("/analysis-runs") && method === "GET") {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/model-providers")) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    });

    return { counts: () => ({ createRun, createJourney }) };
  }

  test.beforeAll(() => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("capture visual baseline screenshots", async ({ page }) => {
    const api = await mockApis(page);

    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, "books-1920x1080-scene.png"),
      fullPage: true,
    });

    await page.setViewportSize({ width: 1280, height: 720 });
    await page.getByTestId("journey-phase-3").click();
    await expect(page.getByTestId("journey-phase-detail-panel")).toBeVisible();
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, "books-1280x720-phase.png"),
      fullPage: true,
    });

    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve",
    );
    await expect(page.getByTestId("journey-detail-empty")).toBeVisible({ timeout: 15000 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, "books-1024x768-empty-state.png"),
      fullPage: true,
    });

    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(
      "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await page.screenshot({
      path: resolve(SCREENSHOT_DIR, "standalone-1920x1080-scene.png"),
      fullPage: true,
    });

    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-export-root")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("journey-export-root").screenshot({
      path: resolve(SCREENSHOT_DIR, "png-export-reader-journey-v2.7.png"),
    });

    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });
});
