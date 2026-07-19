import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.5.1 Reader Journey blocking UI fix", () => {
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
              display_title: "第一章",
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
            chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
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
                raw_text: "第十四景。",
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

    return { counts: () => ({ createRun, createJourney }) };
  }

  function boxesOverlap(
    a: { x: number; y: number; width: number; height: number },
    b: { x: number; y: number; width: number; height: number },
  ) {
    return !(
      a.x + a.width <= b.x ||
      b.x + b.width <= a.x ||
      a.y + a.height <= b.y ||
      b.y + b.height <= a.y
    );
  }

  async function assertNoChromeOverlap(page: import("@playwright/test").Page) {
    const ids = [
      "journey-analysis-header",
      "journey-summary-cards",
      "journey-curve-toolbar",
      "journey-curve-section",
    ];
    const boxes = [];
    for (const id of ids) {
      const el = page.getByTestId(id);
      await expect(el).toBeVisible();
      const box = await el.boundingBox();
      expect(box, id).toBeTruthy();
      boxes.push({ id, ...box! });
    }
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect(
          boxesOverlap(boxes[i]!, boxes[j]!),
          `${boxes[i]!.id} overlaps ${boxes[j]!.id}`,
        ).toBe(false);
      }
    }
  }

  for (const viewport of [
    { width: 1920, height: 1080 },
    { width: 1280, height: 720 },
  ]) {
    test(`scenario A: no overlap at ${viewport.width}x${viewport.height}`, async ({ page }) => {
      const api = await mockApis(page);
      await page.setViewportSize(viewport);
      await page.goto(
        "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=12&overview=curve",
      );
      await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("journey-analysis-title")).toContainText("旅程分析");
      await expect(page.getByTestId("overview-mode-curve")).toHaveCount(0);
      await expect(page.getByTestId("overview-mode-questions")).toHaveCount(0);
      await expect(page.getByTestId("overview-mode-diagnosis")).toHaveCount(0);
      await expect(page.getByTestId("journey-marker-compact")).toBeVisible();
      await expect(page.getByTestId("journey-marker-full")).toBeVisible();
      await expect(page.getByTestId("summary-card-traction")).toBeVisible();
      await expect(page.getByTestId("summary-card-peak")).toBeVisible();
      await expect(page.getByTestId("summary-card-weak")).toBeVisible();
      await expect(page.getByTestId("summary-card-hook")).toBeVisible();
      await expect(page.getByTestId("journey-metric-select")).toBeVisible();
      await page.getByTestId("journey-metric-select").click();
      await expect(page.getByTestId("journey-metric-payoff")).toBeVisible();
      await expect(page.getByTestId("journey-metric-hook")).toBeVisible();
      await expect(page.getByTestId("journey-metric-dropoff_risk")).toBeVisible();
      await expect(page.getByTestId("journey-metric-valence")).toBeVisible();
      await expect(page.getByTestId("journey-curve-node-12")).toBeVisible();
      await assertNoChromeOverlap(page);
      expect(api.counts().createRun).toBe(0);
      expect(api.counts().createJourney).toBe(0);
    });
  }

  test("scenario B: PNG export from legacy questions URL stays on journey analysis", async ({
    page,
  }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=12&overview=questions",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page).toHaveURL(/overview=curve/);

    const downloadPromise = page.waitForEvent("download", { timeout: 15000 });
    const more = page.getByTestId("book-more-menu-trigger");
    if (await more.isVisible().catch(() => false)) {
      await more.click();
      await page.getByTestId("book-more-export-png").click();
    } else {
      await page.getByTestId("journey-export-png").click();
    }

    await expect(page.getByTestId("journey-export-png")).toHaveText(/导出中|导出PNG/);
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^StoryLens_.+_旅程分析_v1\.1\.png$/);

    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page.getByTestId("journey-export-root")).toHaveAttribute(
      "data-overview-mode",
      "curve",
    );
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 12");
    await expect(page).toHaveURL(/overview=curve/);
    await expect(page).toHaveURL(/scene=12/);
    await expect(page.getByTestId("journey-export-feedback")).toBeVisible();
    await expect(page.locator("text=Unexpected Application Error")).toHaveCount(0);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario C: export failure shows feedback and restores UI", async ({ page }) => {
    const api = await mockApis(page);
    await page.addInitScript(() => {
      HTMLCanvasElement.prototype.toBlob = function toBlob(cb) {
        cb(null);
      };
    });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=12&overview=questions",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();

    await page.getByTestId("journey-export-png").click();
    await expect(page.getByTestId("journey-export-feedback")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-export-feedback")).toHaveAttribute(
      "data-status",
      "failed",
    );
    await expect(page.getByTestId("journey-export-png")).toBeEnabled();
    await expect(page.getByTestId("journey-export-png")).toHaveText("导出PNG");
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await expect(page.getByTestId("journey-export-root")).toHaveAttribute(
      "data-overview-mode",
      "curve",
    );
    await expect(page.locator("text=Unexpected Application Error")).toHaveCount(0);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("independent results route: no overlap on curve", async ({ page }) => {
    await mockApis(page);
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(
      "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=12&overview=curve",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-overview-curve")).toBeVisible();
    await assertNoChromeOverlap(page);
  });
});
