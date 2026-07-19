import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.6 journey analysis focused view", () => {
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

  test("scenario A: Books embedded route shows single journey analysis", async ({ page }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-analysis-title")).toContainText("旅程分析");
    await expect(page.getByTestId("overview-mode-curve")).toHaveCount(0);
    await expect(page.getByTestId("overview-mode-questions")).toHaveCount(0);
    await expect(page.getByTestId("overview-mode-diagnosis")).toHaveCount(0);
    await expect(page.getByTestId("summary-card-traction")).toBeVisible();
    await expect(page.getByTestId("summary-card-peak")).toBeVisible();
    await expect(page.getByTestId("summary-card-weak")).toBeVisible();
    await expect(page.getByTestId("summary-card-hook")).toBeVisible();
    await expect(page.getByTestId("journey-phase-1")).toBeVisible();
    await expect(page.getByTestId("journey-phase-4")).toBeVisible();
    await expect(page.getByTestId("journey-curve-svg")).toBeVisible();
    await expect(page.getByTestId("journey-detail-pane")).toBeVisible();
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario B: legacy overview=questions normalizes without blank or new run", async ({
    page,
  }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&paragraph=B0001-C0002-P0090&inspector=scene&overview=questions&metric=curiosity",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-analysis-title")).toContainText("旅程分析");
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page).toHaveURL(/overview=curve/);
    await expect(page).toHaveURL(/scene=9/);
    await expect(page).toHaveURL(/paragraph=B0001-C0002-P0090/);
    await expect(page).toHaveURL(/inspector=scene/);
    await expect(page).toHaveURL(/metric=curiosity/);
    await expect(page.locator("text=Unexpected Application Error")).toHaveCount(0);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario C: legacy overview=diagnosis normalizes", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&inspector=scene&overview=diagnosis",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page).toHaveURL(/overview=curve/);
    await expect(page).toHaveURL(/scene=9/);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario D: metric selector updates curve and URL", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&metric=engagement",
    );
    await expect(page.getByTestId("journey-metric-select")).toBeVisible({ timeout: 15000 });

    for (const [key, label] of [
      ["curiosity", "好奇"],
      ["tension", "紧张"],
      ["payoff", "回报"],
      ["dropoff_risk", "掉线风险"],
      ["engagement", "阅读牵引"],
    ] as const) {
      await page.getByTestId("journey-metric-select").click();
      await page.getByTestId(`journey-metric-${key}`).click();
      await expect(page.getByTestId("journey-metric-select")).toContainText(label);
      await expect(page).toHaveURL(new RegExp(`metric=${key}`));
    }
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario E: Scene click stays stable for 3s", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-curve-node-10")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("journey-curve-node-10").click();
    await expect(page).toHaveURL(/scene=10/);
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 10");
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/scene=10/);
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 10");
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario F: PNG export uses 旅程分析 title", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("journey-export-title")).toContainText("旅程分析");
    const before = page.url();
    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    await page.getByTestId("journey-export-png").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/旅程分析/);
    expect(download.suggestedFilename()).not.toMatch(/曲线总览|问题簇|章节诊断/);
    expect(page.url()).toBe(before);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario G: independent results route same layout", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=9&overview=diagnosis",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-analysis-title")).toContainText("旅程分析");
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page).toHaveURL(/overview=curve/);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });
});
