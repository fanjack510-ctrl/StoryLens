import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

test.describe("Phase 1C-C.2.6.2 compact phase navigation", () => {
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

    return {
      visualization,
      counts: () => ({ createRun, createJourney }),
    };
  }

  const booksUrl =
    "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=9&overview=curve";

  test("scenario A: 1920×1080 four phases visible, equal height, no vertical clip", async ({
    page,
  }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(booksUrl);
    await expect(page.getByTestId("journey-phase-strip")).toBeVisible({ timeout: 15000 });
    const heights: number[] = [];
    for (const n of [1, 2, 3, 4]) {
      const card = page.getByTestId(`journey-phase-${n}`);
      await expect(card).toBeVisible();
      const box = await card.boundingBox();
      expect(box?.height ?? 99).toBeGreaterThanOrEqual(60);
      expect(box?.height ?? 99).toBeLessThanOrEqual(76);
      heights.push(box?.height ?? 0);
      const titleClip = await card.locator(".journey-phase-title").evaluate((el) => {
        const style = window.getComputedStyle(el);
        return {
          overflow: style.overflow,
          whiteSpace: style.whiteSpace,
          textOverflow: style.textOverflow,
          clientHeight: (el as HTMLElement).clientHeight,
          scrollHeight: (el as HTMLElement).scrollHeight,
        };
      });
      expect(titleClip.whiteSpace).toBe("nowrap");
      expect(titleClip.textOverflow).toBe("ellipsis");
      expect(titleClip.scrollHeight - titleClip.clientHeight).toBeLessThanOrEqual(1);
    }
    expect(new Set(heights.map((h) => Math.round(h))).size).toBe(1);
    const curve = await page.getByTestId("journey-curve-svg").boundingBox();
    expect(curve?.height ?? 0).toBeGreaterThanOrEqual(280);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario B: 1280×720 single-row strip, page not horizontally scrolled", async ({
    page,
  }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1280, height: 720 });
    await page.goto(booksUrl);
    await expect(page.getByTestId("journey-phase-1")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-phase-mobile-select-wrap")).toBeHidden();
    const strip = page.getByTestId("journey-phase-strip");
    const layout = await strip.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        display: style.display,
        autoFlow: style.gridAutoFlow,
        overflowX: style.overflowX,
        templateColumns: style.gridTemplateColumns,
      };
    });
    expect(layout.display).toBe("grid");
    // Either 4 columns or mid-width column flow — never 2×2 block growth via wrap.
    const isFourCol = layout.templateColumns.split(" ").filter(Boolean).length === 4;
    const isScrollRow = layout.autoFlow.includes("column") || layout.overflowX === "auto";
    expect(isFourCol || isScrollRow).toBe(true);
    const pageScroll = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(pageScroll.scrollWidth - pageScroll.clientWidth).toBeLessThanOrEqual(2);
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario C: narrow phase select keeps scene, switches inspector", async ({ page }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 640, height: 900 });
    await page.goto(booksUrl);
    // Sync mobile tabs default to 正文; switch to 旅程 so phase nav mounts.
    await expect(page.getByTestId("journey-split-tab-journey")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("journey-split-tab-journey").click();
    await expect(page.getByTestId("journey-phase-mobile-select")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-phase-strip")).toBeHidden();
    await page.getByTestId("journey-phase-mobile-select").selectOption("4");
    await expect(page).toHaveURL(/inspector=phase/);
    await expect(page).toHaveURL(/scene=9/);
    await expect(page.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "phase");
    await expect(page.getByTestId("journey-phase-detail-panel")).toBeVisible();
    await expect(page.getByTestId("phase-detail-title")).toContainText("Phase 4");
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario D: long title uses ellipsis and title tooltip", async ({ page }) => {
    const longTitle = "意识觉醒与身份迷雾以及超长阶段标题用于验证省略号截断效果ABCDEF";
    const api = await mockApis(page, (viz) => {
      viz.phases[0].title = longTitle;
    });
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(booksUrl);
    const card = page.getByTestId("journey-phase-1");
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card).toHaveAttribute("title", longTitle);
    const title = card.locator(".journey-phase-title");
    await expect(title).toHaveCSS("text-overflow", "ellipsis");
    await expect(title).toHaveCSS("white-space", "nowrap");
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("scenario E: PNG export keeps four-column phase strip without mobile select", async ({
    page,
  }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(booksUrl);
    await expect(page.getByTestId("journey-export-png")).toBeVisible({ timeout: 15000 });
    const downloadPromise = page.waitForEvent("download", { timeout: 20000 });
    await page.getByTestId("journey-export-png").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/旅程分析|ReaderJourney|png/i);
    // After export, live DOM should still expose four phase cards (export forced 4-col CSS).
    for (const n of [1, 2, 3, 4]) {
      await expect(page.getByTestId(`journey-phase-${n}`)).toBeVisible();
    }
    await expect(page.getByTestId("journey-phase-mobile-select-wrap")).toBeHidden();
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });

  test("standalone route still loads compact phase nav", async ({ page }) => {
    const api = await mockApis(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(
      "/analysis-runs/55/results?tab=reader-journey&mode=sync&scene=9&overview=curve",
    );
    await expect(page.getByTestId("journey-phase-strip")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-phase-1")).toBeVisible();
    expect(api.counts().createRun).toBe(0);
    expect(api.counts().createJourney).toBe(0);
  });
});
