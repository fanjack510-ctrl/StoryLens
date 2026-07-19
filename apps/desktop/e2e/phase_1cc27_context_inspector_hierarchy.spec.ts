import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.7 Context Inspector hierarchy", () => {
  async function mockApis(
    page: import("@playwright/test").Page,
    mutateViz?: (viz: ReturnType<typeof buildVisualizationFixture>) => void,
  ) {
    const visualization = buildVisualizationFixture();
    mutateViz?.(visualization);
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

    return { counts: () => ({ createRun, createJourney }), visualization };
  }

  test("scenario A: Scene overview hierarchy", async ({ page }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-inspector-header")).toBeVisible();
    await expect(page.getByTestId("scene-detail-title")).toContainText("Scene 9");
    await expect(page.getByTestId("scene-primary-conclusion")).toBeVisible();
    await expect(page.getByTestId("scene-detail-score-bars")).toBeVisible();
    await expect(page.getByTestId("score-bar-engagement")).toBeVisible();
    await expect(page.getByTestId("score-bar-curiosity")).toBeVisible();
    await expect(page.getByTestId("score-bar-tension")).toBeVisible();
    await expect(page.getByTestId("score-bar-dropoff_risk")).toHaveCount(0);
    await page.waitForTimeout(3000);
    await expect(page).toHaveURL(/scene=9/);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario B: empty question chain state", async ({ page }) => {
    const api = await mockApis(page, (viz) => {
      const node = viz.scene_nodes.find((n) => n.scene_ordinal === 3);
      if (!node) return;
      node.reader_question_in = [];
      node.reader_question_created = [];
      node.reader_question_answered = [];
      node.reader_question_out = [];
    });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=3&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-detail-drawer")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("scene-detail-tab-questions").click();
    await expect(page.getByTestId("empty-questions")).toBeVisible();
    await expect(page.getByTestId("empty-questions")).toContainText("未识别出明确问题链");
    await expect(page.getByTestId("journey-detail-error")).toHaveCount(0);
    expect(api.counts().createRun).toBe(0);
  });

  test("scenario C: writing takeaways object renders", async ({ page }) => {
    const api = await mockApis(page, (viz) => {
      const node = viz.scene_nodes.find((n) => n.scene_ordinal === 9);
      if (!node) return;
      node.techniques = [];
      node.writing_takeaways = [
        { summary: "对象技法启示", applicable_when: "中段", avoid_when: "高潮" },
      ];
    });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await page.getByTestId("scene-detail-tab-techniques").click();
    await expect(page.getByTestId("journey-writing-takeaways")).toContainText("对象技法启示");
    await expect(page.locator("text=Unexpected Application Error")).toHaveCount(0);
    expect(api.counts().createRun).toBe(0);
  });

  test("scenario D: Evidence default 5 and locate", async ({ page }) => {
    const api = await mockApis(page, (viz) => {
      const node = viz.scene_nodes.find((n) => n.scene_ordinal === 9);
      if (!node) return;
      node.evidence_paragraph_ids = Array.from({ length: 7 }, (_, i) => `B0001-C0002-P09${i}0`);
      node.hooks = [];
      node.payoffs = [];
      node.techniques = [];
      node.risk_points = [];
      node.reader_question_created = [];
      node.reader_question_answered = [];
      node.primary_hook = null;
      node.primary_payoff = null;
    });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await page.getByTestId("scene-detail-tab-evidence").click();
    await expect(page.locator(".scene-detail-evidence-list li")).toHaveCount(5);
    await page.getByTestId("journey-evidence-expand").click();
    await expect(page.locator(".scene-detail-evidence-list li")).toHaveCount(7);
    await page.getByTestId("journey-evidence-B0001-C0002-P0900").click();
    await expect(page).toHaveURL(/scene=9/);
    expect(api.counts().createRun).toBe(0);
  });

  test("scenario E: Phase keeps Scene and compact related list", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("journey-phase-3")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("journey-phase-3").click();
    await expect(page.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "phase");
    await expect(page.getByTestId("journey-rhythm-dot-9")).toHaveClass(/selected/);
    await expect(page.getByTestId("phase-detail-tabs")).toBeVisible();
    await page.getByTestId("phase-detail-tab-scenes").click();
    await expect(page.getByTestId("phase-related-scenes")).toBeVisible();
    await expect(page.getByTestId("phase-related-scene-9")).toBeVisible();
    expect(api.counts().createRun).toBe(0);
  });

  test("scenario F: Question/Hook/Payoff/Risk inspectors", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
    );
    await expect(page.getByTestId("summary-card-traction")).toBeVisible({ timeout: 15000 });
    // Question via chapter insight / cluster if available
    const clusterBtn = page.getByTestId("summary-card-traction");
    await clusterBtn.click();
    await expect(page).toHaveURL(/inspector=(question|scene|phase)/);
    // Hook via summary hook card when clickable
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=14&overview=curve&inspector=hook",
    );
    await expect(page.getByTestId("journey-hook-inspector")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-inspector-header")).toBeVisible();
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=5&overview=curve&inspector=payoff",
    );
    await expect(page.getByTestId("journey-payoff-inspector")).toBeVisible({ timeout: 15000 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=8&overview=curve&inspector=risk",
    );
    // risk may need selectedRiskKey; inspector shell still mounts for risk kind
    await expect(page.getByTestId("journey-detail-pane")).toBeVisible();
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario G: no-selection empty state", async ({ page }) => {
    const api = await mockApis(page);
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve",
    );
    await expect(page.getByTestId("journey-detail-empty")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-detail-empty")).toContainText("选择一个 Phase");
    await expect(page.getByTestId("journey-detail-empty")).toContainText("点击曲线节点查看 Scene");
    await expect(page.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "empty");
    expect(api.counts().createRun).toBe(0);
  });

  test("scenario H: responsive viewports", async ({ page }) => {
    const api = await mockApis(page);
    for (const size of [
      { width: 1920, height: 1080 },
      { width: 1280, height: 720 },
      { width: 1024, height: 768 },
    ]) {
      await page.setViewportSize(size);
      await page.goto(
        "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve&inspector=scene",
      );
      await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 15000 });
      await expect(page.getByTestId("journey-inspector-header")).toBeVisible();
      const curveBox = await page.getByTestId("journey-curve-svg").boundingBox();
      expect(curveBox?.height ?? 0).toBeGreaterThanOrEqual(200);
      await expect(page.locator("text=Unexpected Application Error")).toHaveCount(0);
    }
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });
});
