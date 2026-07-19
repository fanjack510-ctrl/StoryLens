import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.4 Reader Journey UI refinement", () => {
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

    return {
      counts: () => ({ createRun, createJourney }),
    };
  }

  test("embedded books route: overview fixed, detail tabs, evidence, export", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=12",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("structured-chapter-text-pane")).toBeVisible();
    await expect(page.getByTestId("journey-overview-pane")).toBeVisible();
    await expect(page.getByTestId("journey-detail-pane")).toBeVisible();
    await expect(page.getByTestId("journey-active-scene-guide")).toBeVisible();
    await expect(page.getByTestId("journey-summary-cards")).toBeVisible();

    await expect(page.getByTestId("journey-rhythm-dot-14")).toBeVisible();
    await page.getByTestId("structured-scene-header-14").click();
    await expect(page).toHaveURL(/scene=14/);
    await expect(page.getByTestId("sync-paragraph-B0001-C0002-P0064")).toBeVisible();

    await page.getByTestId("scene-detail-tab-questions").click();
    await expect(page.getByTestId("scene-detail-questions")).toBeVisible();
    await page.getByTestId("scene-detail-tab-payoffs").click();
    await expect(page.getByTestId("scene-detail-payoffs")).toBeVisible();
    await page.getByTestId("scene-detail-tab-evidence").click();
    const evidence = page.locator('[data-testid^="journey-evidence-"]').first();
    if (await evidence.count()) {
      await evidence.click();
    }

    await page.getByTestId("journey-marker-full").click();
    await expect(page.getByTestId("journey-marker-full")).toHaveClass(/active/);
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 14");

    await page.getByTestId("journey-export-png").click();
    await page.reload();
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page).toHaveURL(/scene=14/);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("independent results route still shows refined journey UI", async ({ page }) => {
    await mockApis(page);
    await page.goto("/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=12");
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-overview-pane")).toBeVisible();
    await expect(page.getByTestId("journey-active-scene-guide")).toBeVisible();
    await expect(page.getByTestId("scene-detail-tabs")).toBeVisible();
  });
});
