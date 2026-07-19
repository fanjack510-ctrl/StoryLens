import { expect, test } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";
import {
  buildFixture13Scenes,
  buildFixture30Scenes,
} from "../src/components/readerJourney/mockVisualizationFixtures";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const SCREENSHOT_DIR = resolve(
  __dirname,
  "../../../audits/single-chapter-pipeline/reader-journey-visual-regression-v2.9",
);

test.describe("Reader Journey Visualization v2.9 DOM screenshots", () => {
  async function mockApis(
    page: import("@playwright/test").Page,
    visualization: ReturnType<typeof buildVisualizationFixture> | ReturnType<typeof buildFixture13Scenes>,
  ) {
    const scenes = buildScenes();
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
            progress_current: visualization.scene_nodes.length,
            progress_total: visualization.scene_nodes.length,
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
            completed_scene_count: visualization.scene_nodes.length,
            total_scene_count: visualization.scene_nodes.length,
          },
        });
      }
      if (url.includes("/analysis-runs/55/reader-journey") && method === "POST") {
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
            summary: { total_scene_count: visualization.scene_nodes.length },
            scenes,
          },
        });
      }
      if (url.includes("/scenes") && method === "GET") {
        return route.fulfill({ json: scenes });
      }
      if (url.includes("/model-providers")) return route.fulfill({ json: [] });
      if (url.includes("/analysis-runs") && method === "GET") {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({ json: {} });
    });
  }

  test.beforeAll(() => {
    mkdirSync(SCREENSHOT_DIR, { recursive: true });
  });

  test("13 Scene default / collapsed / expanded / 0-100 / PNG root", async ({ page }) => {
    const visualization = buildFixture13Scenes();
    await mockApis(page, visualization);
    await page.addInitScript(() => {
      localStorage.setItem("storylens.readerJourney.inspectorCollapsed.v2_9", "true");
      localStorage.setItem("storylens.readerJourney.chartHeight.v2_9", JSON.stringify("standard"));
      localStorage.setItem("storylens.readerJourney.yDomainMode.v2_9", JSON.stringify("fixed_0_100"));
    });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve",
    );
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("journey-curve-svg")).toHaveAttribute("height", "408");
    await expect(page.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "true",
    );
    for (let i = 1; i <= 13; i += 1) {
      await expect(page.getByTestId(`journey-curve-node-${i}`)).toBeVisible();
    }

    await page.getByTestId("journey-workspace").screenshot({
      path: resolve(SCREENSHOT_DIR, "01-13-scene-standard-default.png"),
    });
    await page.getByTestId("journey-inspector-summary-bar").screenshot({
      path: resolve(SCREENSHOT_DIR, "02-13-scene-inspector-collapsed.png"),
    });
    await page.getByTestId("journey-curve-section").screenshot({
      path: resolve(SCREENSHOT_DIR, "04-13-scene-full-0-100-curve.png"),
    });

    await page.getByTestId("journey-inspector-summary-expand").click();
    await expect(page.getByTestId("journey-resizable-split")).toHaveAttribute(
      "data-inspector-collapsed",
      "false",
    );
    await page.getByTestId("journey-workspace").screenshot({
      path: resolve(SCREENSHOT_DIR, "03-13-scene-inspector-expanded.png"),
    });

    await page.getByTestId("journey-export-full-root").screenshot({
      path: resolve(SCREENSHOT_DIR, "06-png-full-export-root.png"),
    });

    const metrics = await page.evaluate(() => {
      const svg = document.querySelector('[data-testid="journey-curve-svg"]');
      const container = document.querySelector('[data-testid="journey-curve-container"]');
      const style = container ? window.getComputedStyle(container) : null;
      return {
        svgHeight: svg?.getAttribute("height"),
        plotArea: document
          .querySelector('[data-testid="journey-curve-section"]')
          ?.getAttribute("data-plot-area-height"),
        overflowY: style?.overflowY,
        nodeCount: document.querySelectorAll('[data-testid^="journey-curve-node-"]').length,
      };
    });
    writeFileSync(
      resolve(SCREENSHOT_DIR, "dom-metrics-13.json"),
      JSON.stringify(metrics, null, 2),
      "utf8",
    );
    expect(metrics.svgHeight).toBe("408");
    expect(metrics.plotArea).toBe("340");
    expect(metrics.overflowY).toMatch(/hidden|visible/);
    expect(metrics.nodeCount).toBe(13);
  });

  test("30 Scene horizontal browse", async ({ page }) => {
    const visualization = buildFixture30Scenes();
    expect(visualization.scene_nodes.length).toBe(30);
    await mockApis(page, visualization);
    await page.addInitScript(() => {
      localStorage.setItem("storylens.readerJourney.inspectorCollapsed.v2_9", "true");
    });
    await page.setViewportSize({ width: 1280, height: 1000 });
    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&overview=curve",
    );
    await expect(page.getByTestId("journey-curve-svg")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("journey-analysis-subtitle")).toContainText("30个Scene");
    await expect(page.getByTestId("journey-y-tick-0")).toBeVisible();
    await expect(page.getByTestId("journey-y-tick-100")).toBeVisible();
    await expect(page.getByTestId("journey-curve-node-30")).toBeVisible();
    await page.getByTestId("journey-workspace").screenshot({
      path: resolve(SCREENSHOT_DIR, "05-30-scene-horizontal-browse.png"),
    });
  });
});
