import { test, expect } from "@playwright/test";
import { buildVisualizationFixture } from "../fixtures/readerJourneyE2eFixtures";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";
import { findDirtyVisibleToken } from "../../src/services/auditDirtyVisibleText";

test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

const JOURNEY_BOOK = "/books/1?chapter=1&analysisRun=55&view=result&tab=reader-journey&mode=journey";

const FORBIDDEN_VISIBLE = [
  /\bundefined\b/i,
  /\bnull\b/i,
  /\bNaN\b/,
  /\[object Object\]/,
  /\bPhase\b/,
  /Scene\s*#/,
  /Current Metric/i,
  /Task Control/i,
  /Curve ID/i,
];

async function assertNoForbiddenVisible(page: import("@playwright/test").Page) {
  // Scan primary journey chrome only — technical details may keep raw keys.
  const root = page.getByTestId("journey-workspace");
  const text = (await root.innerText()).replace(/分析信息[\s\S]*$/, "");
  for (const re of FORBIDDEN_VISIBLE) {
    expect(text, `forbidden visible pattern ${re}`).not.toMatch(re);
  }
  const dirty = findDirtyVisibleToken(text);
  expect(dirty).toBeNull();
}

async function installJourneyReadyRoute(page: import("@playwright/test").Page) {
  const visualization = buildVisualizationFixture();
  await page.route("**/api/v1/analysis-runs/55/reader-journey**", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return route.fulfill({
        json: {
          journey_run_id: 701,
          analysis_run_id: 55,
          status: "succeeded",
          visualization,
          scene_nodes: visualization.scene_nodes,
          chapter_summary: visualization.chapter_summary,
          one_sentence_diagnosis: visualization.chapter_summary?.diagnosis ?? "审计旅程诊断",
        },
      });
    }
    if (method === "POST") {
      return route.fulfill({
        status: 202,
        json: { journey_run_id: 701, status: "running", analysis_run_id: 55 },
      });
    }
    return route.fulfill({ json: {} });
  });
  await page.route("**/reader-journey-runs/701/progress**", async (route) => {
    return route.fulfill({
      json: {
        journey_run_id: 701,
        analysis_run_id: 55,
        status: "succeeded",
        total_scene_count: 14,
        completed_scene_count: 14,
        remaining_scene_count: 0,
        phase_count: 4,
        has_chapter_summary: true,
        retryable: false,
      },
    });
  });
  await page.route("**/api/v1/analysis-runs/55/results**", async (route) => {
    return route.fulfill({
      json: {
        run: { id: 55, status: "succeeded", provider: "audit", model: "audit" },
        chapter: {
          id: 1,
          book_id: 1,
          title: "第一章　潮汐钟",
          display_title: "第一章　潮汐钟",
        },
        boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1 },
        summary: { total_scene_count: 14, evidence_coverage_rate: 1 },
        scenes: Array.from({ length: 14 }, (_, i) => ({
          scene: {
            id: 100 + i + 1,
            ordinal: i + 1,
            scene_key: `scene-${i + 1}`,
            start_paragraph_id: `B0001-C0001-P${String((i + 1) * 10).padStart(4, "0")}`,
            end_paragraph_id: `B0001-C0001-P${String((i + 1) * 10 + 2).padStart(4, "0")}`,
          },
          analysis_artifact: null,
        })),
      },
    });
  });
  return visualization;
}

test.describe("06 reader journey", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("not generated", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "none", tasks: "empty" });
    await gotoReady(page, JOURNEY_BOOK);
    const cta = page.getByTestId("generate-reader-journey");
    if (await cta.count()) await cta.waitFor();
    await shot(page, { id: "06-01", file: "06_reader_journey_empty.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-01b", file: "06_rj_not_generated.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("generating", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "generating" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-progress").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await shot(page, { id: "06-02", file: "06_reader_journey_loading.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-02b", file: "06_rj_generating.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("failed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "failed" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-failed").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await shot(page, { id: "06-05", file: "06_reader_journey_failed.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-05b", file: "06_rj_failed.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("success workspace interactions", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    const visualization = await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 });

    await expect(page.getByTestId("journey-analysis-title")).toContainText("阅读旅程");
    const chart = page.getByTestId("journey-curve-svg");
    await expect(chart).toBeVisible();
    const chartBox = await chart.boundingBox();
    expect(chartBox?.width ?? 0).toBeGreaterThanOrEqual(700);
    await expect(page.getByTestId("journey-curve-node-1")).toBeVisible();

    const workspaceBox = await page.getByTestId("journey-workspace").boundingBox();
    expect(workspaceBox?.width ?? 0).toBeGreaterThanOrEqual(900);

    await assertNoForbiddenVisible(page);
    await shot(page, {
      id: "06-03",
      file: "06_reader_journey_success.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await shot(page, { id: "06-03b", file: "06_rj_success.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-03c", file: "06_reader_journey_default.png", route: JOURNEY_BOOK, theme: "light" });

    const engagementBefore = visualization.curve_series.engagement?.[0]?.value;
    await page.getByTestId("journey-metric-segment-engagement").click();
    await shot(page, {
      id: "06-09a",
      file: "06_reader_journey_metric_reading-pull.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await page.getByTestId("journey-metric-segment-arousal").click();
    await expect(page.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "arousal",
    );
    await shot(page, {
      id: "06-09",
      file: "06_reader_journey_metric_emotion.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await page.getByTestId("journey-metric-segment-tension").click();
    await shot(page, {
      id: "06-11",
      file: "06_reader_journey_metric_pacing.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await page.getByTestId("journey-metric-segment-hook").click();
    await shot(page, {
      id: "06-10",
      file: "06_reader_journey_metric_hook.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    expect(visualization.curve_series.engagement?.[0]?.value).toBe(engagementBefore);

    await page.getByTestId("journey-phase-2").click();
    await expect(page.getByTestId("journey-phase-2")).toHaveClass(/selected|active-phase/);
    await shot(page, {
      id: "06-13",
      file: "06_reader_journey_phase_selected.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });

    await page.getByTestId("journey-curve-node-4").click();
    await shot(page, {
      id: "06-14",
      file: "06_reader_journey_node_selected.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await shot(page, {
      id: "06-14b",
      file: "06_reader_journey_scene_selected.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });

    const hoverNode = page.getByTestId("journey-curve-node-8");
    await hoverNode.focus();
    await hoverNode.hover({ force: true });
    const tooltipHost = page.getByTestId("journey-node-tooltip");
    const tooltip = page.locator(".journey-node-tooltip-card");
    if (await tooltipHost.count()) {
      await expect(tooltip).toBeVisible();
      const tipText = await tooltip.innerText();
      expect(tipText).toMatch(/场景|阅读牵引|情绪|节奏|钩子/);
      expect(tipText).not.toMatch(/undefined|NaN/);
      const tipBox = await tooltip.boundingBox();
      const vp = page.viewportSize();
      if (tipBox && vp) {
        expect(tipBox.x).toBeGreaterThanOrEqual(0);
        expect(tipBox.y).toBeGreaterThanOrEqual(0);
        expect(tipBox.x + tipBox.width).toBeLessThanOrEqual(vp.width + 2);
      }
      await shot(page, {
        id: "06-07",
        file: "06_reader_journey_tooltip.png",
        route: JOURNEY_BOOK,
        theme: "light",
      });
    }

    const widthOpen = (await page.getByTestId("journey-curve-svg").boundingBox())?.width ?? 0;
    const collapse = page.getByTestId("journey-collapse-inspector").first();
    if (await collapse.count()) {
      await collapse.click();
      await expect(page.getByTestId("journey-inspector-summary-expand")).toBeVisible();
      const widthCollapsed =
        (await page.getByTestId("journey-curve-svg").boundingBox())?.width ?? 0;
      expect(widthCollapsed).toBeGreaterThanOrEqual(widthOpen - 1);
      await shot(page, {
        id: "06-15",
        file: "06_reader_journey_detail_collapsed.png",
        route: JOURNEY_BOOK,
        theme: "light",
      });
      await page.getByTestId("journey-inspector-summary-expand").click();
      await shot(page, {
        id: "06-15b",
        file: "06_reader_journey_detail_open.png",
        route: JOURNEY_BOOK,
        theme: "light",
      });
    }

    const task = page.getByTestId("journey-task-controls");
    if (await task.count()) {
      await task.locator("summary").click();
      await shot(page, {
        id: "06-16",
        file: "06_reader_journey_task_open.png",
        route: JOURNEY_BOOK,
        theme: "light",
      });
    }

    await shot(page, {
      id: "06-12",
      file: "06_reader_journey_long.png",
      route: JOURNEY_BOOK,
      theme: "light",
      fullPage: true,
    });
  });

  test("1024 layout", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 800 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 });
    const chartBox = await page.getByTestId("journey-curve-svg").boundingBox();
    expect(chartBox?.width ?? 0).toBeGreaterThanOrEqual(560);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);
    await shot(page, {
      id: "06-17",
      file: "06_reader_journey_1024.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
  });

  test("dark theme", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 });
    await shot(page, {
      id: "06-18",
      file: "06_reader_journey_dark.png",
      route: JOURNEY_BOOK,
      theme: "dark",
    });
    const node = page.getByTestId("journey-curve-node-4");
    await node.hover();
    await shot(page, {
      id: "06-19",
      file: "06_reader_journey_tooltip_dark.png",
      route: JOURNEY_BOOK,
      theme: "dark",
    });
    const collapse = page.getByTestId("journey-collapse-inspector").first();
    if (await collapse.count()) {
      await shot(page, {
        id: "06-20",
        file: "06_reader_journey_detail_dark.png",
        route: JOURNEY_BOOK,
        theme: "dark",
      });
    }
  });

  test("empty journey detail", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "empty" });
    await gotoReady(page, JOURNEY_BOOK);
    await shot(page, {
      id: "06-04",
      file: "06_rj_empty_detail.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
  });
});
