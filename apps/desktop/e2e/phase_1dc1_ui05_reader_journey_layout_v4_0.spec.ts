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
  "../../../audits/single-chapter-pipeline/reader-journey-visual-regression-v4.0",
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
    "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=journey&overview=curve",
  );
  await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("journey-workspace")).toHaveAttribute(
    "data-visualization-version",
    "4.0",
  );
}

async function captureLayoutAudit(page: Page) {
  return page.evaluate(() => {
    const pick = (sel: string) => {
      const el = document.querySelector(sel) as HTMLElement | null;
      if (!el) return null;
      const cs = getComputedStyle(el);
      return {
        display: cs.display,
        position: cs.position,
        clientWidth: el.clientWidth,
        clientHeight: el.clientHeight,
        scrollWidth: el.scrollWidth,
        scrollHeight: el.scrollHeight,
        overflowX: cs.overflowX,
        overflowY: cs.overflowY,
        minWidth: cs.minWidth,
        maxWidth: cs.maxWidth,
        minHeight: cs.minHeight,
        maxHeight: cs.maxHeight,
        zIndex: cs.zIndex,
        flex: cs.flex,
        gridTemplateColumns: cs.gridTemplateColumns,
      };
    };
    const svgEl = document.querySelector(
      '[data-testid="journey-curve-svg"]',
    ) as SVGSVGElement | null;
    const chartEl = document.querySelector(
      '[data-testid="journey-curve-svg"]',
    ) as SVGSVGElement | null;
    const mainEl = document.querySelector(
      '[data-testid="journey-main-pane"]',
    ) as HTMLElement | null;
    const rawChart = chartEl?.getBoundingClientRect();
    const mainBox = mainEl?.getBoundingClientRect();
    // Clip SVG box to MainPane — overflow:hidden may leave layout boxes extending under the dock.
    const chartBox =
      rawChart && mainBox
        ? {
            left: Math.max(rawChart.left, mainBox.left),
            top: Math.max(rawChart.top, mainBox.top),
            right: Math.min(rawChart.right, mainBox.right),
            bottom: Math.min(rawChart.bottom, mainBox.bottom),
          }
        : rawChart;
    const inspector = document.querySelector(
      '[data-testid="journey-inspector-pane"]:not([hidden]), [data-testid="journey-inspector-dock"]',
    ) as HTMLElement | null;
    const inspectorBox = inspector?.getBoundingClientRect();
    const layout = document
      .querySelector('[data-testid="journey-workspace"]')
      ?.getAttribute("data-layout");
    // Overlay only if the inspector rectangle covers the SVG interior (not mere adjacency).
    let overlapsChart = false;
    if (chartBox && inspectorBox && inspectorBox.width > 8 && inspectorBox.height > 8) {
      const ix = Math.max(chartBox.left, inspectorBox.left);
      const iy = Math.max(chartBox.top, inspectorBox.top);
      const ax = Math.min(chartBox.right, inspectorBox.right);
      const ay = Math.min(chartBox.bottom, inspectorBox.bottom);
      const area = Math.max(0, ax - ix) * Math.max(0, ay - iy);
      overlapsChart = area > 64; // ignore 1–2px border/seam contact
    }
    return {
      appShell: pick('[data-testid="app-shell"]'),
      workspace: pick('[data-testid="journey-workspace"]'),
      grid: pick('[data-testid="journey-workspace-grid"]'),
      source: pick('[data-testid="journey-source-pane"]'),
      main: pick('[data-testid="journey-main-pane"]'),
      toolbar: pick('[data-testid="journey-curve-toolbar"]'),
      shell: pick('[data-testid="journey-chart-shell"]'),
      viewport: pick('[data-testid="journey-chart-viewport"]'),
      inspector: pick('[data-testid="journey-inspector-pane"]') ?? pick('[data-testid="journey-inspector-dock"]'),
      svg: svgEl
        ? {
            height: svgEl.getAttribute("height"),
            viewBox: svgEl.getAttribute("viewBox"),
          }
        : null,
      toolRailPresent: !!document.querySelector('[data-testid="journey-chart-tool-rail"]'),
      forbiddenLabels: ["指", "全", "P", "详", "出"].filter((label) => {
        const buttons = Array.from(
          document.querySelectorAll('[data-testid="journey-curve-toolbar"] button'),
        );
        return buttons.some((b) => (b.textContent || "").trim() === label);
      }),
      inspectorOverlapsChart: overlapsChart,
      layout,
      chartBox: chartBox
        ? { left: chartBox.left, top: chartBox.top, right: chartBox.right, bottom: chartBox.bottom }
        : null,
      inspectorBox: inspectorBox
        ? {
            left: inspectorBox.left,
            top: inspectorBox.top,
            right: inspectorBox.right,
            bottom: inspectorBox.bottom,
            width: inspectorBox.width,
            height: inspectorBox.height,
          }
        : null,
      nodeCount: document.querySelectorAll('[data-testid^="journey-curve-node-"]').length,
    };
  });
}

test.describe("Phase 1D-C1-UI-05 Reader Journey Workspace Layout v4.0", () => {
  test.beforeAll(() => {
    fs.mkdirSync(OUT, { recursive: true });
  });

  test("1920 inspector closed + open; toolbar labels; no rail; no overlay", async ({
    page,
  }, testInfo) => {
    testInfo.setTimeout(180_000);
    await openJourney(page, 13, 1920, 1080);

    await expect(page.getByTestId("journey-curve-toolbar")).toBeVisible();
    await expect(page.getByTestId("journey-zoom-fit-all")).toHaveText("适应全部");
    await expect(page.getByTestId("journey-zoom-focus-phase")).toHaveText("当前Phase");
    await expect(page.getByTestId("journey-inspector-toggle")).toHaveText("查看详情");
    await expect(page.getByTestId("journey-export-png")).toHaveText("导出PNG");
    await expect(page.getByTestId("journey-more-chart-settings")).toHaveText("更多设置");
    await expect(page.getByTestId("journey-chart-tool-rail")).toHaveCount(0);

    await expect(page.getByTestId("journey-curve-svg")).toHaveAttribute("height", "420");
    for (const tick of [0, 25, 50, 75, 100]) {
      await expect(page.getByTestId(`journey-y-tick-${tick}`)).toBeVisible();
    }

    await page.screenshot({
      path: path.join(OUT, "01-1920-inspector-closed.png"),
      fullPage: true,
    });

    let audit = await captureLayoutAudit(page);
    expect(audit.toolRailPresent).toBe(false);
    expect(audit.forbiddenLabels).toEqual([]);
    expect(audit.nodeCount).toBe(13);
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1920-closed.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );

    await page.getByTestId("journey-inspector-summary-expand").click();
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    await expect(page.getByTestId("journey-curve-svg")).toHaveAttribute("height", "420");

    const shell = page.getByTestId("journey-chart-shell");
    const inspector = page
      .locator('[data-testid="journey-inspector-pane"]:not([hidden]), [data-testid="journey-inspector-dock"]')
      .first();
    await expect(inspector).toBeVisible();
    expect(await shell.evaluate((el, other) => el.contains(other as Node), await inspector.elementHandle())).toBe(
      false,
    );
    const inspectorPosition = await inspector.evaluate((el) => getComputedStyle(el).position);
    expect(["static", "relative", "sticky"]).toContain(inspectorPosition);

    audit = await captureLayoutAudit(page);
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1920-open.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );
    // Peer dock must not paint over the SVG plot (horizontal dock or vertical bottom dock).
    expect(audit.inspectorOverlapsChart).toBe(false);

    await page.screenshot({
      path: path.join(OUT, "02-1920-inspector-open.png"),
      fullPage: true,
    });
    await page.getByTestId("journey-curve-toolbar").screenshot({
      path: path.join(OUT, "03-toolbar-full-labels.png"),
    });
  });

  test("1600 and 1366 mid layout bottom dock", async ({ page }, testInfo) => {
    testInfo.setTimeout(180_000);

    await openJourney(page, 13, 1600, 900);
    await page.getByTestId("journey-inspector-summary-expand").click();
    await page.screenshot({
      path: path.join(OUT, "04-1600-inspector-open.png"),
      fullPage: true,
    });

    await openJourney(page, 13, 1366, 768);
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", /mid|narrow|desktop/);
    await page.screenshot({
      path: path.join(OUT, "05-1366-inspector-closed.png"),
      fullPage: true,
    });
    const expand = page.getByTestId("journey-inspector-summary-expand");
    if (await expand.count()) {
      await expand.click();
    } else {
      await page.getByTestId("journey-inspector-toggle").click();
    }
    await page.waitForTimeout(250);
    const midAudit = await captureLayoutAudit(page);
    expect(midAudit.inspectorOverlapsChart).toBe(false);
    await page.screenshot({
      path: path.join(OUT, "06-1366-bottom-dock.png"),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1366-dock.json"),
      JSON.stringify({ ...midAudit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );
  });

  test("more menu viewport clamp + 30 scene browse + phase strip", async ({ page }, testInfo) => {
    testInfo.setTimeout(180_000);
    await openJourney(page, 13, 1920, 1080);

    await page.getByTestId("journey-more-chart-settings").click();
    const panel = page.getByTestId("journey-more-menu-panel");
    await expect(panel).toBeVisible();
    const box = await panel.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(1920);
    await page.screenshot({
      path: path.join(OUT, "07-more-menu-right-edge.png"),
      fullPage: true,
    });
    await page.keyboard.press("Escape");

    await page.getByTestId("journey-phase-strip").screenshot({
      path: path.join(OUT, "08-phase-horizontal.png"),
    });

    await openJourney(page, 30, 1440, 960);
    await expect(page.getByTestId("journey-y-tick-0")).toBeVisible();
    await page.getByTestId("journey-chart-viewport").evaluate((el) => {
      el.scrollLeft = 160;
    });
    await page.screenshot({
      path: path.join(OUT, "09-30-scene-horizontal-browse.png"),
      fullPage: true,
    });
  });

  test("13 scene full curve shell screenshot", async ({ page }, testInfo) => {
    testInfo.setTimeout(120_000);
    await openJourney(page, 13, 1920, 1080);
    await page.getByTestId("journey-chart-shell").screenshot({
      path: path.join(OUT, "10-13-scene-full-curve.png"),
    });
    await expect(page.getByTestId("journey-curve-container")).toHaveAttribute(
      "data-plot-height",
      "352",
    );
  });
});
