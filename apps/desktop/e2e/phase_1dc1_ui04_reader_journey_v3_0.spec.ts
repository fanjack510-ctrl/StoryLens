import { expect, test, type Page } from "@playwright/test";
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
  "../../../audits/single-chapter-pipeline/reader-journey-visual-regression-v3.0",
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

async function openJourney(page: Page, sceneCount: number) {
  await mockApis(page, sceneCount);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto(
    "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=journey&overview=curve",
  );
  await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 20000 });
  await expect(page.getByTestId("journey-chart-shell")).toBeVisible();
}

async function assertYTicksVisible(page: Page) {
  for (const tick of [0, 25, 50, 75, 100]) {
    const el = page.getByTestId(`journey-y-tick-${tick}`);
    await expect(el).toBeVisible();
    const box = await el.boundingBox();
    expect(box, `tick ${tick} box`).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(960);
  }
}

test.describe("Phase 1D-C1-UI-04 Reader Journey Visualization v3.0", () => {
  test("13-scene full Y axis + tool rail + inspector states (DOM screenshots)", async ({
    page,
  }, testInfo) => {
    testInfo.setTimeout(120_000);
    await openJourney(page, 13);

    const svg = page.getByTestId("journey-curve-svg");
    await expect(svg).toHaveAttribute("height", "420");
    await expect(page.getByTestId("journey-curve-container")).toHaveAttribute(
      "data-plot-height",
      "352",
    );
    await expect(page.getByTestId("journey-chart-tool-rail")).toBeVisible();
    await expect(page.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );

    await assertYTicksVisible(page);

    const metrics = await page.evaluate(() => {
      const pick = (sel: string) => {
        const el = document.querySelector(sel) as HTMLElement | null;
        if (!el) return null;
        const cs = getComputedStyle(el);
        return {
          clientWidth: el.clientWidth,
          clientHeight: el.clientHeight,
          scrollWidth: el.scrollWidth,
          scrollHeight: el.scrollHeight,
          overflowX: cs.overflowX,
          overflowY: cs.overflowY,
          minHeight: cs.minHeight,
          maxHeight: cs.maxHeight,
          height: cs.height,
        };
      };
      const svgEl = document.querySelector(
        '[data-testid="journey-curve-svg"]',
      ) as SVGSVGElement | null;
      const clip = document.querySelector("#journey-plot-clip rect");
      return {
        workspace: pick('[data-testid="journey-workspace"]'),
        shell: pick('[data-testid="journey-chart-shell"]'),
        viewport: pick('[data-testid="journey-chart-viewport"]'),
        container: pick('[data-testid="journey-curve-container"]'),
        svg: svgEl
          ? {
              width: svgEl.getAttribute("width"),
              height: svgEl.getAttribute("height"),
              viewBox: svgEl.getAttribute("viewBox"),
              clientHeight: svgEl.clientHeight,
            }
          : null,
        clipHeight: clip?.getAttribute("height") ?? null,
        nodeCount: document.querySelectorAll('[data-testid^="journey-curve-node-"]').length,
      };
    });

    expect(metrics.svg?.height).toBe("420");
    expect(Number(metrics.clipHeight)).toBe(352);
    expect(metrics.nodeCount).toBe(13);
    expect(metrics.container?.overflowY).toBe("hidden");
    expect(metrics.shell?.clientHeight ?? 0).toBeGreaterThanOrEqual(440);

    await page.screenshot({
      path: path.join(OUT, "01-13-scene-full-y-axis.png"),
      fullPage: true,
    });
    await page.getByTestId("journey-chart-shell").screenshot({
      path: path.join(OUT, "02-13-scene-y-ticks-0-25-visible.png"),
    });
    await page.getByTestId("journey-curve-svg").screenshot({
      path: path.join(OUT, "03-13-scene-trough-visible.png"),
    });
    await page.screenshot({
      path: path.join(OUT, "04-13-scene-inspector-collapsed.png"),
      fullPage: true,
    });

    await page.getByTestId("journey-inspector-summary-expand").click();
    await expect(page.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    await expect(svg).toHaveAttribute("height", "420");
    await page.screenshot({
      path: path.join(OUT, "05-13-scene-inspector-expanded.png"),
      fullPage: true,
    });

    await page.getByTestId("journey-chart-tool-rail").screenshot({
      path: path.join(OUT, "06-vertical-tool-rail.png"),
    });

    // Persist metrics for audit
    const fs = await import("node:fs");
    fs.mkdirSync(OUT, { recursive: true });
    fs.writeFileSync(
      path.join(OUT, "dom-metrics-13.json"),
      JSON.stringify({ ...metrics, capturedAt: new Date().toISOString() }, null, 2),
      "utf8",
    );
  });

  test("30-scene horizontal browse DOM screenshot", async ({ page }, testInfo) => {
    testInfo.setTimeout(120_000);
    await openJourney(page, 30);
    await expect(page.getByTestId("journey-y-tick-0")).toBeVisible();
    await expect(page.getByTestId("journey-y-tick-25")).toBeVisible();
    await page.getByTestId("journey-curve-container").evaluate((el) => {
      el.scrollLeft = 120;
    });
    await page.screenshot({
      path: path.join(OUT, "07-30-scene-horizontal-browse.png"),
      fullPage: true,
    });
  });
});
