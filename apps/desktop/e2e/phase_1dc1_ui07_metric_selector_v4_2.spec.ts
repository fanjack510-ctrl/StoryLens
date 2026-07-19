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
  "../../../audits/single-chapter-pipeline/reader-journey-metric-selector-visual-regression-v4.2",
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
  ) as typeof base.curve_series;
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
    "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve&metric=engagement",
  );
  await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("journey-workspace")).toHaveAttribute(
    "data-visualization-version",
    "4.2",
  );
}

async function openInspector(page: Page) {
  const expand = page.getByTestId("journey-inspector-summary-expand");
  if (await expand.count()) {
    await expand.click();
  } else {
    const toggle = page.getByTestId("journey-inspector-toggle");
    if (await toggle.count()) await toggle.click();
  }
  await page.waitForTimeout(200);
}

async function metricOverlapAudit(page: Page) {
  return page.evaluate(() => {
    const panel = document.querySelector(
      '[data-testid="journey-metric-select-menu"]',
    ) as HTMLElement | null;
    const phase = document.querySelector(
      '[data-testid="journey-phase-strip"]',
    ) as HTMLElement | null;
    const chart = document.querySelector(
      '[data-testid="journey-curve-svg"]',
    ) as SVGSVGElement | null;
    const trigger = document.querySelector(
      '[data-testid="journey-metric-select"]',
    ) as HTMLElement | null;
    const morePanel = document.querySelector(
      '[data-testid="journey-more-menu-panel"]',
    ) as HTMLElement | null;

    function overlapArea(a: DOMRect, b: DOMRect) {
      const ix = Math.max(a.left, b.left);
      const iy = Math.max(a.top, b.top);
      const ax = Math.min(a.right, b.right);
      const ay = Math.min(a.bottom, b.bottom);
      return Math.max(0, ax - ix) * Math.max(0, ay - iy);
    }

    const panelBox = panel?.getBoundingClientRect();
    const phaseBox = phase?.getBoundingClientRect();
    const chartBox = chart?.getBoundingClientRect();
    const moreBox = morePanel?.getBoundingClientRect();
    const style = panel ? getComputedStyle(panel) : null;

    return {
      panelOpen: !!panel,
      panelPosition: style?.position ?? null,
      panelBackground: style?.backgroundColor ?? null,
      panelOpaque:
        style != null &&
        style.backgroundColor !== "transparent" &&
        style.backgroundColor !== "rgba(0, 0, 0, 0)",
      panelInFlow: panel?.getAttribute("data-metric-panel") === "in-flow",
      overlapsPhase:
        panelBox && phaseBox ? overlapArea(panelBox, phaseBox) > 4 : false,
      overlapsChart:
        panelBox && chartBox ? overlapArea(panelBox, chartBox) > 4 : false,
      phaseBelowPanel:
        panelBox && phaseBox ? phaseBox.top >= panelBox.bottom - 1 : null,
      chartBelowPhase:
        phaseBox && chartBox ? chartBox.top >= phaseBox.bottom - 2 : null,
      metricLabel: trigger?.textContent?.replace(/\s+/g, " ").trim() ?? null,
      ariaExpanded: trigger?.getAttribute("aria-expanded"),
      svgHeight: chart?.getAttribute("height"),
      moreInViewport:
        moreBox != null
          ? moreBox.left >= 0 &&
            moreBox.right <= window.innerWidth + 1 &&
            moreBox.top >= 0 &&
            moreBox.bottom <= window.innerHeight + 1
          : null,
      overlayRoot: !!document.getElementById("journey-overlay-root"),
      viewport: { w: window.innerWidth, h: window.innerHeight },
    };
  });
}

test.describe("Phase 1D-C1-UI-07 Metric Selector Overlay System v4.2", () => {
  test.beforeAll(() => {
    fs.mkdirSync(OUT, { recursive: true });
  });

  test("metric panel closed / open / select / viewports", async ({ page }, testInfo) => {
    testInfo.setTimeout(240_000);

    await openJourney(page, 13, 1920, 1080);
    let audit = await metricOverlapAudit(page);
    expect(audit.panelOpen).toBe(false);
    expect(audit.svgHeight).toBe("420");
    await page.screenshot({ path: path.join(OUT, "01-metric-closed-1920.png"), fullPage: true });

    await page.getByTestId("journey-metric-select").click();
    await expect(page.getByTestId("journey-metric-select-menu")).toBeVisible();
    audit = await metricOverlapAudit(page);
    expect(audit.panelInFlow).toBe(true);
    expect(audit.panelPosition).toBe("static");
    expect(audit.panelOpaque).toBe(true);
    expect(audit.overlapsPhase).toBe(false);
    expect(audit.overlapsChart).toBe(false);
    expect(audit.phaseBelowPanel).toBe(true);
    await page.screenshot({ path: path.join(OUT, "02-metric-open-1920.png"), fullPage: true });
    await page.screenshot({
      path: path.join(OUT, "03-metric-open-phase-visible.png"),
      fullPage: true,
    });
    await page.screenshot({
      path: path.join(OUT, "04-metric-open-chart-visible.png"),
      fullPage: true,
    });

    await page.getByTestId("journey-metric-hook").click();
    await expect(page.getByTestId("journey-metric-select-menu")).toHaveCount(0);
    await expect(page.getByTestId("journey-metric-select")).toHaveAttribute(
      "data-current-metric",
      "hook",
    );
    expect(page.url()).toMatch(/metric=hook/);
    await page.screenshot({ path: path.join(OUT, "05-metric-selected-closed.png"), fullPage: true });

    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1920.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );

    await openJourney(page, 13, 1600, 900);
    await page.getByTestId("journey-metric-select").click();
    audit = await metricOverlapAudit(page);
    expect(audit.overlapsPhase).toBe(false);
    expect(audit.overlapsChart).toBe(false);
    await page.screenshot({ path: path.join(OUT, "06-1600x900-open.png"), fullPage: true });

    await openJourney(page, 13, 1366, 768);
    await page.getByTestId("journey-metric-select").click();
    audit = await metricOverlapAudit(page);
    expect(audit.overlapsPhase).toBe(false);
    expect(audit.overlapsChart).toBe(false);
    await page.screenshot({ path: path.join(OUT, "07-1366x768-open.png"), fullPage: true });
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-1366.json"),
      JSON.stringify({ ...audit, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );

    await openJourney(page, 13, 1000, 800);
    await expect(page.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "narrow", {
      timeout: 10000,
    });
    await expect(page.getByTestId("journey-workspace-tabs")).toBeVisible();
    // DOM evaluate avoids hidden inspector-pane intercepting Playwright pointer clicks
    await page.evaluate(() => {
      const tab = document.querySelector(
        '[data-testid="journey-tab-main"]',
      ) as HTMLButtonElement | null;
      tab?.click();
      const trigger = document.querySelector(
        '[data-testid="journey-metric-select"]',
      ) as HTMLButtonElement | null;
      trigger?.click();
    });
    await expect(page.getByTestId("journey-metric-select-menu")).toBeVisible({ timeout: 5000 });
    audit = await metricOverlapAudit(page);
    expect(audit.panelOpen).toBe(true);
    expect(["static", "relative"]).toContain(audit.panelPosition);
    expect(audit.overlapsPhase).toBe(false);
    expect(audit.panelInFlow).toBe(true);
    await expect(page.getByTestId("journey-more-chart-settings")).toBeVisible();
    await page.screenshot({ path: path.join(OUT, "08-narrow-metric-panel.png"), fullPage: true });
  });

  test("inspector open + source max + more settings collision", async ({ page }, testInfo) => {
    testInfo.setTimeout(180_000);
    await openJourney(page, 13, 1920, 1080);
    await openInspector(page);
    await page.getByTestId("journey-metric-select").click();
    let audit = await metricOverlapAudit(page);
    expect(audit.overlapsPhase).toBe(false);
    expect(audit.overlapsChart).toBe(false);
    await page.screenshot({
      path: path.join(OUT, "09-inspector-open-metric-panel.png"),
      fullPage: true,
    });

    await page.keyboard.press("Escape");
    const left = page.getByTestId("journey-splitter-source");
    await left.focus();
    await page.keyboard.press("End");
    await page.getByTestId("journey-metric-select").click();
    audit = await metricOverlapAudit(page);
    expect(audit.overlapsPhase).toBe(false);
    await page.screenshot({
      path: path.join(OUT, "10-source-max-metric-panel.png"),
      fullPage: true,
    });

    await page.keyboard.press("Escape");
    await page.getByTestId("journey-more-chart-settings").click();
    await expect(page.getByTestId("journey-more-menu-panel")).toBeVisible();
    audit = await metricOverlapAudit(page);
    expect(audit.moreInViewport).toBe(true);
    expect(audit.overlayRoot).toBe(true);
    await page.screenshot({ path: path.join(OUT, "11-more-settings-edge.png"), fullPage: true });

    await expect(page.getByTestId("journey-curve-svg")).toHaveAttribute("height", "420");
    for (const tick of [0, 25, 50, 75, 100]) {
      await expect(page.getByTestId(`journey-y-tick-${tick}`)).toBeVisible();
    }
  });
});
