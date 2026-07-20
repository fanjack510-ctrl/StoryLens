import { test, expect, type Page } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { buildVisualizationFixture } from "../fixtures/readerJourneyE2eFixtures";
import { installUiAuditMocks } from "./helpers/mockApi";
import {
  shot,
  prepareAuditSession,
  gotoReady,
  applyProductTheme,
  assertRealDarkTheme,
  SCREENSHOT_DIR,
} from "./helpers/shot";
import { findDirtyVisibleToken } from "../../src/services/auditDirtyVisibleText";

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

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
  /AnalysisRun/i,
  /JourneyRun/i,
  /Scene Profiles/i,
  /\brunning\b/,
  /\bsucceeded\b/,
  /Scene summary/i,
  /所属 Phase/,
  /相关Scene/,
];

async function assertNoForbiddenVisible(page: Page) {
  const root = page.getByTestId("journey-workspace");
  if (!(await root.count())) return;
  // Strip developer/analysis info and tech details from the ordinary-UI scan.
  const text = (await root.innerText())
    .replace(/分析信息[\s\S]*?(?=阅读牵引|入局|展开详情|$)/, "")
    .replace(/visualization v[\s\S]*?(?=阅读牵引|入局|展开详情|$)/, "")
    .replace(/技术详情[\s\S]*$/, "");
  for (const re of FORBIDDEN_VISIBLE) {
    expect(text, `forbidden visible pattern ${re}`).not.toMatch(re);
  }
  const dirty = findDirtyVisibleToken(text);
  expect(dirty).toBeNull();
}

async function resetJourneyScroll(page: Page) {
  await page.evaluate(() => {
    window.scrollTo(0, 0);
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
    const main = document.querySelector(".journey-main-pane, .journey-workspace");
    if (main instanceof HTMLElement) main.scrollTop = 0;
  });
  await page.waitForTimeout(80);
}

async function installJourneyReadyRoute(page: Page) {
  const visualization = buildVisualizationFixture();
  // Inject phase summaries that would previously render as "."
  visualization.phases = visualization.phases.map((phase, i) =>
    i === 0 ? { ...phase, summary: "." } : phase,
  );
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

function fileSha256(file: string): string {
  const buf = fs.readFileSync(path.join(SCREENSHOT_DIR, file));
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function assertScreenshotsDiffer(a: string, b: string, label: string) {
  const pathA = path.join(SCREENSHOT_DIR, a);
  const pathB = path.join(SCREENSHOT_DIR, b);
  if (!fs.existsSync(pathA) || !fs.existsSync(pathB)) return;
  expect(fileSha256(a), `${label}: ${a} vs ${b} must differ`).not.toBe(fileSha256(b));
}

test.describe("06 reader journey", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("empty result state", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "empty", tasks: "empty" });
    await gotoReady(page, JOURNEY_BOOK);
    const empty = page.getByTestId("journey-empty-state");
    await expect(empty).toBeVisible({ timeout: 15_000 });
    await expect(empty).toContainText("暂时没有可显示的阅读旅程");
    await expect(page.getByTestId("journey-curve-svg")).toHaveCount(0);
    await expect(page.getByTestId("unified-recovery-card")).toHaveCount(0);
    await shot(page, {
      id: "06-01",
      file: "06_reader_journey_empty.png",
      route: JOURNEY_BOOK,
      theme: "light",
      checkDirtyVisible: true,
    });
  });

  test("not generated / analysis paused", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "none", tasks: "empty" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("unified-recovery-card").waitFor({ timeout: 15_000 }).catch(() => undefined);
    await shot(page, {
      id: "06-01p",
      file: "06_reader_journey_analysis_paused.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await shot(page, { id: "06-01b", file: "06_rj_not_generated.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("generating", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "generating" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("reader-journey-progress-card").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await page.getByTestId("journey-progress").waitFor({ timeout: 5_000 }).catch(() => undefined);
    const body = await page.locator("body").innerText();
    expect(body).toMatch(/正在生成阅读旅程|正在处理场景|已处理/);
    expect(body).not.toMatch(/0\s*\/\s*0/);
    expect(body.replace(/技术详情[\s\S]*/, "")).not.toMatch(/AnalysisRun|JourneyRun|\brunning\b/);
    await shot(page, { id: "06-02", file: "06_reader_journey_loading.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-02b", file: "06_rj_generating.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("failed", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "failed" });
    await gotoReady(page, JOURNEY_BOOK);
    const failed = page.getByTestId("journey-failed");
    await expect(failed).toBeVisible({ timeout: 15_000 });
    await expect(failed).toContainText("阅读旅程生成失败");
    await expect(failed).toContainText("已完成的场景分析不会受到影响");
    await expect(page.getByTestId("journey-failed-retry")).toBeVisible();
    await expect(page.getByTestId("journey-failed-task-details")).toBeVisible();
    await expect(page.getByTestId("journey-curve-svg")).toHaveCount(0);
    await expect(page.getByTestId("journey-empty-state")).toHaveCount(0);
    await shot(page, { id: "06-05", file: "06_reader_journey_failed.png", route: JOURNEY_BOOK, theme: "light" });
    await shot(page, { id: "06-05b", file: "06_rj_failed.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("success workspace interactions", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    const visualization = await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 });
    await resetJourneyScroll(page);

    await expect(page.getByTestId("journey-analysis-title")).toContainText("阅读旅程");
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "desktop");
    const chart = page.getByTestId("journey-curve-svg");
    await expect(chart).toBeVisible();
    const chartBox = await chart.boundingBox();
    expect(chartBox?.width ?? 0).toBeGreaterThanOrEqual(700);

    // Phase "." fallback must show structural Chinese, not a lone period.
    const phase1 = page.getByTestId("journey-phase-1");
    await expect(phase1).toContainText(/建立背景|阅读期待/);
    await expect(phase1).not.toHaveText(/^\s*\.\s*$/);

    // Open inspector (defaults collapsed) and assert right-side layout at 1440.
    await page.getByTestId("journey-curve-node-1").click();
    const inspector = page.getByTestId("journey-inspector-pane");
    await expect(inspector).toBeVisible();
    await expect(inspector).toHaveAttribute("data-dock", "right");
    const inspectorBox = await inspector.boundingBox();
    const chartAfter = await chart.boundingBox();
    expect(inspectorBox).toBeTruthy();
    expect(chartAfter).toBeTruthy();
    if (inspectorBox && chartAfter) {
      expect(inspectorBox.x).toBeGreaterThan(chartAfter.x + chartAfter.width - 8);
    }
    await expect(page.getByTestId("journey-inspector-close")).toHaveCount(0);
    // Collapse again for a clean default shot of the main curve.
    await page.getByTestId("journey-collapse-inspector").first().click();
    await expect(page.getByTestId("journey-inspector-summary-expand")).toBeVisible();

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

    await resetJourneyScroll(page);
    await page.getByTestId("journey-phase-2").click();
    await expect(page.getByTestId("journey-phase-2")).toHaveClass(/selected|active-phase/);
    await shot(page, {
      id: "06-13",
      file: "06_reader_journey_phase_selected.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });

    // Scene selection via rhythm strip (scene entrance) — distinct from node click only if UI differs.
    // Product: both open the same scene inspector → mark node as same_interaction after capturing scene.
    await resetJourneyScroll(page);
    const rhythm = page.getByTestId("journey-rhythm-dot-4");
    if (await rhythm.count()) {
      await rhythm.click();
    } else {
      await page.getByTestId("journey-curve-node-4").click();
    }
    await expect(page.getByTestId("scene-detail-title")).toContainText(/场景 04/);
    const sceneIdBefore = visualization.scene_nodes.find((n) => n.scene_ordinal === 4)?.scene_id;
    expect(sceneIdBefore).toBe(104);
    await shot(page, {
      id: "06-14b",
      file: "06_reader_journey_scene_selected.png",
      route: JOURNEY_BOOK,
      theme: "light",
      notes: "scene entrance selection",
    });

    // Node click is the same inspector interaction in current product — do not fake a second state.
    // Active-scene overlay can intercept SVG pointer events; force confirms the same Scene ID remains.
    await page.getByTestId("journey-curve-node-4").click({ force: true });
    await expect(page.getByTestId("scene-detail-title")).toContainText(/场景 04/);
    // Write a same_interaction note instead of a duplicate screenshot with a different name.
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    fs.writeFileSync(
      path.join(SCREENSHOT_DIR, "06_reader_journey_node_selected.same_interaction.json"),
      JSON.stringify({
        status: "same_interaction",
        same_as: "06_reader_journey_scene_selected.png",
        reason: "Curve node click and scene entrance both open JourneySceneDetailPanel for the same Scene ID.",
      }),
      "utf8",
    );

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

    await resetJourneyScroll(page);
    const widthOpen = (await page.getByTestId("journey-curve-svg").boundingBox())?.width ?? 0;
    const collapse = page.getByTestId("journey-collapse-inspector").first();
    await expect(collapse).toBeVisible();
    await collapse.click();
    await expect(page.getByTestId("journey-inspector-summary-expand")).toBeVisible();
    const widthCollapsed =
      (await page.getByTestId("journey-curve-svg").boundingBox())?.width ?? 0;
    expect(widthCollapsed).toBeGreaterThan(widthOpen);
    await shot(page, {
      id: "06-15",
      file: "06_reader_journey_detail_collapsed.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
    await page.getByTestId("journey-inspector-summary-expand").click();
    await expect(page.getByTestId("scene-detail-title")).toContainText(/场景 04/);
    await shot(page, {
      id: "06-15b",
      file: "06_reader_journey_detail_open.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });

    const task = page.getByTestId("journey-task-controls");
    if (await task.count()) {
      await task.locator("summary").first().click();
      const taskText = (await task.innerText()).replace(/技术详情[\s\S]*$/, "");
      expect(taskText).not.toMatch(/\brunning\b|\bsucceeded\b|AnalysisRun|Scene Analysis/i);
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
    await resetJourneyScroll(page);

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 1);

    for (const ordinal of [1, 2, 3, 4]) {
      const card = page.getByTestId(`journey-phase-${ordinal}`);
      await expect(card).toBeVisible();
      const box = await card.boundingBox();
      expect(box, `phase ${ordinal} clipped`).toBeTruthy();
      if (box) {
        expect(box.x + box.width).toBeLessThanOrEqual(clientWidth + 2);
        expect(box.width).toBeGreaterThan(40);
      }
    }
    await expect(page.getByTestId("journey-phase-4")).toContainText("收束");

    const chartBox = await page.getByTestId("journey-curve-svg").boundingBox();
    expect(chartBox?.width ?? 0).toBeGreaterThanOrEqual(560);

    const actions = page.locator(".journey-workspace button, .journey-chart-toolbar button");
    const count = await actions.count();
    for (let i = 0; i < Math.min(count, 24); i += 1) {
      const box = await actions.nth(i).boundingBox();
      if (!box || box.width < 2) continue;
      expect(box.x + box.width).toBeLessThanOrEqual(clientWidth + 4);
    }

    await shot(page, {
      id: "06-17",
      file: "06_reader_journey_1024.png",
      route: JOURNEY_BOOK,
      theme: "light",
    });
  });

  test("dark theme real product switch", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 });
    await applyProductTheme(page, "dark");
    await assertRealDarkTheme(page);
    await resetJourneyScroll(page);
    await shot(page, {
      id: "06-18",
      file: "06_reader_journey_dark.png",
      route: JOURNEY_BOOK,
      theme: "dark",
    });

    const node = page.getByTestId("journey-curve-node-4");
    await node.hover({ force: true });
    const tooltip = page.locator(".journey-node-tooltip-card");
    if (await tooltip.count()) {
      await expect(tooltip).toBeVisible();
      const bg = await tooltip.evaluate((el) => getComputedStyle(el).backgroundColor);
      expect(bg).not.toMatch(/^rgb\(\s*255,\s*255,\s*255\s*\)$/);
    }
    await shot(page, {
      id: "06-19",
      file: "06_reader_journey_tooltip_dark.png",
      route: JOURNEY_BOOK,
      theme: "dark",
    });

    await page.getByTestId("journey-curve-node-4").click();
    await expect(page.getByTestId("journey-detail-pane")).toBeVisible();
    const detailBg = await page
      .getByTestId("journey-detail-pane")
      .evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(detailBg).not.toMatch(/^rgb\(\s*255,\s*255,\s*255\s*\)$/);
    await shot(page, {
      id: "06-20",
      file: "06_reader_journey_detail_dark.png",
      route: JOURNEY_BOOK,
      theme: "dark",
    });
  });

  test("screenshot integrity hashes", async () => {
    assertScreenshotsDiffer(
      "06_reader_journey_default.png",
      "06_reader_journey_dark.png",
      "default vs dark",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_tooltip.png",
      "06_reader_journey_tooltip_dark.png",
      "tooltip vs tooltip_dark",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_empty.png",
      "06_reader_journey_failed.png",
      "empty vs failed",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_empty.png",
      "06_reader_journey_analysis_paused.png",
      "empty vs paused",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_failed.png",
      "06_reader_journey_analysis_paused.png",
      "failed vs paused",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_detail_open.png",
      "06_reader_journey_detail_collapsed.png",
      "detail open vs collapsed",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_metric_reading-pull.png",
      "06_reader_journey_metric_emotion.png",
      "metric pull vs emotion",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_metric_reading-pull.png",
      "06_reader_journey_metric_pacing.png",
      "metric pull vs pacing",
    );
    assertScreenshotsDiffer(
      "06_reader_journey_metric_reading-pull.png",
      "06_reader_journey_metric_hook.png",
      "metric pull vs hook",
    );
    // node_selected is same_interaction — must not exist as a duplicate PNG
    expect(
      fs.existsSync(path.join(SCREENSHOT_DIR, "06_reader_journey_node_selected.png")),
    ).toBe(false);
    expect(
      fs.existsSync(
        path.join(SCREENSHOT_DIR, "06_reader_journey_node_selected.same_interaction.json"),
      ),
    ).toBe(true);
  });
});
