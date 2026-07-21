import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(
  __dirname,
  "../../../audits/single-chapter-pipeline/reader-journey-resizable-visual-regression-v4.1",
);

function withSceneCount(sceneCount: number) {
  const base = buildVisualizationFixture();
  const nodes = base.scene_nodes.slice(0, sceneCount).map((node, index) => ({
    ...node,
    scene_ordinal: index + 1,
    scene_id: 1000 + index + 1,
  }));
  const values = nodes.map((_, i) => {
    if (i === 0) return 0;
    if (i === 1) return 10;
    if (i === 2) return 25;
    if (i === Math.floor(sceneCount / 2)) return 100;
    if (i === sceneCount - 2) return 15;
    return 20 + ((i * 11) % 70);
  });
  const series = values.map((value, i) => ({ scene_ordinal: i + 1, value }));
  const curve_series = Object.fromEntries(
    Object.keys(base.curve_series).map((key) => [key, series]),
  ) as unknown as typeof base.curve_series;
  return {
    ...base,
    scene_nodes: nodes,
    curve_series,
    chapter_summary: {
      ...base.chapter_summary,
      peaks: {
        ...base.chapter_summary.peaks,
        engagement_peak: { scene_ordinal: Math.floor(sceneCount / 2) + 1, value: 100 },
        engagement_valley: { scene_ordinal: 1, value: 0 },
      },
    },
  };
}

async function mockApis(page: Page, sceneCount: number) {
  const visualization = withSceneCount(sceneCount);
  const scenes = buildScenes().slice(0, sceneCount).map((scene, index) => ({
    ...scene,
    scene_ordinal: index + 1,
    id: 1000 + index + 1,
  }));
  const paragraphs = buildChapterParagraphs();

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
          progress_current: sceneCount,
          progress_total: sceneCount,
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
          completed_scene_count: sceneCount,
          total_scene_count: sceneCount,
        },
      });
    }
    if (url.includes("/analysis-runs/55/reader-journey")) {
      return route.fulfill({
        json: {
          status: "succeeded",
          journey_run_id: 5,
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
          summary: { total_scene_count: sceneCount },
          scenes,
        },
      });
    }
    if (url.match(/\/scenes\/\d+\/paragraphs/)) {
      return route.fulfill({
        json: {
          paragraphs: [
            {
              id: "B0001-C0002-P0010",
              raw_text: "场景正文。",
              in_scene: true,
              paragraph_index: 10,
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
}

async function openJourney(page: Page, sceneCount: number, width = 1920, height = 1080) {
  await page.addInitScript(() => {
    try {
      localStorage.clear();
    } catch {
      /* ignore */
    }
  });
  await mockApis(page, sceneCount);
  await page.setViewportSize({ width, height });
  await page.goto(
    "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve",
  );
  await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("journey-workspace")).toHaveAttribute(
    "data-visualization-version",
    "4.1",
  );
}

async function openInspector(page: Page) {
  const expand = page.getByTestId("journey-inspector-summary-expand");
  if (await expand.count()) {
    await expand.click();
  } else {
    await page.getByTestId("journey-inspector-toggle").click();
  }
  await page.waitForTimeout(200);
}

async function captureResizeAudit(page: Page) {
  return page.evaluate(() => {
    const workspace = document.querySelector(
      '[data-testid="journey-workspace"]',
    ) as HTMLElement | null;
    const grid = document.querySelector(
      '[data-testid="journey-workspace-grid"]',
    ) as HTMLElement | null;
    const main = document.querySelector(
      '[data-testid="journey-main-pane"]',
    ) as HTMLElement | null;
    const source = document.querySelector(
      '[data-testid="journey-source-pane"]',
    ) as HTMLElement | null;
    const inspector = document.querySelector(
      '[data-testid="journey-inspector-pane"]:not([hidden]), [data-testid="journey-inspector-dock"]',
    ) as HTMLElement | null;
    const svg = document.querySelector(
      '[data-testid="journey-curve-svg"]',
    ) as SVGSVGElement | null;
    const chartBox = svg?.getBoundingClientRect();
    const mainBox = main?.getBoundingClientRect();
    const inspectorBox = inspector?.getBoundingClientRect();
    let overlapsChart = false;
    if (chartBox && inspectorBox && mainBox && inspectorBox.width > 8 && inspectorBox.height > 8) {
      const clipped = {
        left: Math.max(chartBox.left, mainBox.left),
        top: Math.max(chartBox.top, mainBox.top),
        right: Math.min(chartBox.right, mainBox.right),
        bottom: Math.min(chartBox.bottom, mainBox.bottom),
      };
      const ix = Math.max(clipped.left, inspectorBox.left);
      const iy = Math.max(clipped.top, inspectorBox.top);
      const ax = Math.min(clipped.right, inspectorBox.right);
      const ay = Math.min(clipped.bottom, inspectorBox.bottom);
      overlapsChart = Math.max(0, ax - ix) * Math.max(0, ay - iy) > 64;
    }
    return {
      layout: workspace?.getAttribute("data-layout"),
      sourceWidth: grid?.getAttribute("data-source-width"),
      inspectorWidth: grid?.getAttribute("data-inspector-width"),
      mainClientWidth: main?.clientWidth ?? 0,
      sourceClientWidth: source && !source.hidden ? source.clientWidth : 0,
      pageScrollWidth: document.documentElement.scrollWidth,
      pageClientWidth: document.documentElement.clientWidth,
      svgHeight: svg?.getAttribute("height"),
      overlapsChart,
      hasSourceSplitter: !!document.querySelector('[data-testid="journey-splitter-source"]'),
      hasInspectorSplitter: !!document.querySelector('[data-testid="journey-splitter-inspector"]'),
      hasDockSplitter: !!document.querySelector('[data-testid="journey-splitter-dock"]'),
    };
  });
}

test.describe("Phase 1D-C1-UI-06 Reader Journey Resizable Workspace v4.1", () => {
  test.beforeAll(() => {
    fs.mkdirSync(OUT, { recursive: true });
  });

  test("default / min / max pane widths + dual adjust + collapse", async ({ page }, testInfo) => {
    testInfo.setTimeout(180_000);
    await openJourney(page, 13, 1920, 1080);
    await openInspector(page);

    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "desktop");
    await expect(page.getByTestId("journey-splitter-source")).toBeVisible();
    await expect(page.getByTestId("journey-splitter-inspector")).toBeVisible();
    let audit = await captureResizeAudit(page);
    expect(audit.sourceWidth).toBe("300");
    expect(audit.inspectorWidth).toBe("360");
    expect(audit.mainClientWidth).toBeGreaterThanOrEqual(640);
    expect(audit.overlapsChart).toBe(false);
    expect(audit.pageScrollWidth).toBeLessThanOrEqual(audit.pageClientWidth + 1);
    await page.screenshot({ path: path.join(OUT, "01-default-three-pane.png"), fullPage: true });

    const left = page.getByTestId("journey-splitter-source");
    await left.focus();
    await page.keyboard.press("Home");
    audit = await captureResizeAudit(page);
    expect(Number(audit.sourceWidth)).toBe(220);
    expect(audit.mainClientWidth).toBeGreaterThanOrEqual(640);
    await page.screenshot({ path: path.join(OUT, "02-source-min.png"), fullPage: true });

    await page.keyboard.press("End");
    audit = await captureResizeAudit(page);
    expect(Number(audit.sourceWidth)).toBeLessThanOrEqual(480);
    expect(audit.mainClientWidth).toBeGreaterThanOrEqual(640);
    await page.screenshot({ path: path.join(OUT, "03-source-max.png"), fullPage: true });
    await page.keyboard.press("Enter");

    const right = page.getByTestId("journey-splitter-inspector");
    await right.focus();
    await page.keyboard.press("Home");
    audit = await captureResizeAudit(page);
    expect(Number(audit.inspectorWidth)).toBe(300);
    await page.screenshot({ path: path.join(OUT, "04-inspector-min.png"), fullPage: true });

    await page.keyboard.press("End");
    audit = await captureResizeAudit(page);
    expect(Number(audit.inspectorWidth)).toBeLessThanOrEqual(520);
    expect(audit.mainClientWidth).toBeGreaterThanOrEqual(640);
    await page.screenshot({ path: path.join(OUT, "05-inspector-max.png"), fullPage: true });
    await page.keyboard.press("Enter");

    await left.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await right.focus();
    await page.keyboard.press("ArrowRight");
    audit = await captureResizeAudit(page);
    expect(Number(audit.sourceWidth)).toBeGreaterThan(300);
    expect(Number(audit.inspectorWidth)).toBeGreaterThan(360);
    expect(audit.overlapsChart).toBe(false);
    await page.screenshot({ path: path.join(OUT, "06-both-adjusted.png"), fullPage: true });

    await page.getByTestId("journey-source-toggle").click();
    audit = await captureResizeAudit(page);
    expect(audit.hasSourceSplitter).toBe(false);
    expect(Number(audit.sourceWidth)).toBe(0);
    await page.screenshot({ path: path.join(OUT, "07-source-collapsed.png"), fullPage: true });
    await page.getByTestId("journey-source-toggle").click();

    await page.getByTestId("journey-inspector-toggle").click();
    audit = await captureResizeAudit(page);
    expect(audit.hasInspectorSplitter).toBe(false);
    await page.screenshot({ path: path.join(OUT, "08-inspector-collapsed.png"), fullPage: true });

    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1920-resize.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );
  });

  test("1366 bottom dock height + narrow no splitter", async ({ page }, testInfo) => {
    testInfo.setTimeout(180_000);
    await openJourney(page, 13, 1366, 768);
    await openInspector(page);
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "mid");
    await expect(page.getByTestId("journey-splitter-dock")).toBeVisible();
    await expect(page.getByTestId("journey-splitter-inspector")).toHaveCount(0);
    const dock = page.getByTestId("journey-splitter-dock");
    await dock.focus();
    await page.keyboard.press("End");
    let audit = await captureResizeAudit(page);
    expect(audit.overlapsChart).toBe(false);
    await page.screenshot({ path: path.join(OUT, "09-1366-bottom-dock.png"), fullPage: true });
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1366-dock.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );

    await openJourney(page, 13, 1000, 800);
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "narrow");
    await expect(page.getByTestId("journey-splitter-source")).toHaveCount(0);
    await expect(page.getByTestId("journey-workspace-tabs")).toBeVisible();
    audit = await captureResizeAudit(page);
    expect(audit.hasSourceSplitter).toBe(false);
    expect(audit.hasInspectorSplitter).toBe(false);
    await page.screenshot({ path: path.join(OUT, "10-narrow-tabs.png"), fullPage: true });
  });

  test("chart floors and scene preserved while resizing", async ({ page }, testInfo) => {
    testInfo.setTimeout(120_000);
    await openJourney(page, 13, 1920, 1080);
    await page.getByTestId("journey-curve-node-3").click();
    const before = page.url();
    await openInspector(page);
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "desktop");
    const left = page.getByTestId("journey-splitter-source");
    await left.focus();
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("ArrowRight");
    await expect(page.getByTestId("journey-curve-svg")).toHaveAttribute("height", "420");
    for (const tick of [0, 25, 50, 75, 100]) {
      await expect(page.getByTestId(`journey-y-tick-${tick}`)).toBeVisible();
    }
    expect(page.url()).toBe(before);
    const audit = await captureResizeAudit(page);
    expect(audit.overlapsChart).toBe(false);
    expect(audit.svgHeight).toBe("420");
  });
});
