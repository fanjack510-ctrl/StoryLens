import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.6.1 header and insight density", () => {
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
                id: "B0001-C0002-P0064",
                raw_text: "峰值场景。",
                in_scene: true,
                paragraph_index: 64,
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

    return { counts: () => ({ createRun, createJourney }), visualization };
  }

  test("scenario A: single title, compact insights, wide curve", async ({ page }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("journey-analysis-title")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-analysis-subtitle")).toContainText("Scene");
    const visibleTitles = page.locator(
      "h1:visible, h2:visible, h3:visible",
      { hasText: /^旅程分析$/ },
    );
    await expect(visibleTitles).toHaveCount(1);
    await expect(page.getByTestId("journey-export-title")).toBeHidden();
    const strip = page.getByTestId("journey-summary-cards");
    await expect(strip).toHaveAttribute("data-insight-strip", "true");
    const box = await strip.boundingBox();
    expect(box?.height ?? 99).toBeLessThanOrEqual(64);
    const curveBox = await page.getByTestId("journey-curve-svg").boundingBox();
    const paneBox = await page.getByTestId("journey-overview-pane").boundingBox();
    expect(curveBox && paneBox).toBeTruthy();
    if (curveBox && paneBox) {
      expect(curveBox.width / paneBox.width).toBeGreaterThanOrEqual(0.75);
    }
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario B: peak click selects Scene and stays 3s", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("summary-card-peak")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("summary-card-peak").click();
    await expect(page).toHaveURL(/scene=14/);
    await expect(page).toHaveURL(/inspector=scene/);
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 14");
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/scene=14/);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario C: weak interval clicks valley scene", async ({ page }) => {
    const { visualization, counts } = await mockApis(page);
    const valley = visualization.chapter_summary.peaks.engagement_valley.scene_ordinal;
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("summary-card-weak")).toContainText(`最低点 Scene ${valley}`);
    await page.getByTestId("summary-card-weak").click();
    await expect(page).toHaveURL(new RegExp(`scene=${valley}`));
    await expect(page).toHaveURL(/inspector=scene/);
    await expect(page.getByTestId("scene-detail-title")).toContainText(`Scene ${valley}`);
    expect(counts().createRun).toBe(0);
    expect(counts().createJourney).toBe(0);
  });

  test("scenario D: traction and hook open inspectors", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await page.getByTestId("summary-card-traction").click();
    await expect(page.getByTestId("journey-detail-pane")).toHaveAttribute(
      "data-inspector",
      "question",
    );
    await page.getByTestId("summary-card-hook").click();
    await expect(page.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "hook");
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario E: PNG has single title", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.getByTestId("journey-export-png").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/旅程分析/);
    await expect(page.getByTestId("journey-analysis-title")).toBeVisible();
    await expect(page.getByTestId("journey-summary-cards")).toBeVisible();
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });
});
