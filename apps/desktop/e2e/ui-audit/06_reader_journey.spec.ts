import { test, expect } from "@playwright/test";
import { buildVisualizationFixture } from "../fixtures/readerJourneyE2eFixtures";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const JOURNEY_BOOK = "/books/1?chapter=1&analysisRun=55&view=result&tab=reader-journey";

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
        chapter: { id: 1, title: "第一章　潮汐钟", display_title: "第一章　潮汐钟" },
        boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1 },
        summary: { total_scene_count: 14, evidence_coverage_rate: 1 },
        scenes: [],
      },
    });
  });
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
    await shot(page, { id: "06-01", file: "06_rj_not_generated.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("generating", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "generating" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-progress").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await shot(page, { id: "06-02", file: "06_rj_generating.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("failed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "failed" });
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-failed").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await shot(page, { id: "06-05", file: "06_rj_failed.png", route: JOURNEY_BOOK, theme: "light" });
  });

  test("success workspace chart export", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "ready" });
    await installJourneyReadyRoute(page);
    await gotoReady(page, JOURNEY_BOOK);
    await page.getByTestId("journey-workspace").waitFor({ timeout: 20_000 }).catch(() => undefined);
    await shot(page, { id: "06-03", file: "06_rj_success.png", route: JOURNEY_BOOK, theme: "light" });

    const svg = page.getByTestId("journey-curve-svg");
    if (await svg.count()) {
      await shot(page, { id: "06-06", file: "06_rj_chart.png", route: JOURNEY_BOOK, theme: "light" });
      const box = await svg.boundingBox();
      if (box) {
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await shot(page, { id: "06-07", file: "06_rj_node_hover.png", route: JOURNEY_BOOK, theme: "light" });
      }
    }

    const metric = page.getByTestId("journey-metric-select");
    if (await metric.count()) {
      await metric.selectOption({ index: 1 }).catch(() => undefined);
      await shot(page, { id: "06-09", file: "06_rj_emotion.png", route: JOURNEY_BOOK, theme: "light" });
      await metric.selectOption({ index: 2 }).catch(() => undefined);
      await shot(page, { id: "06-10", file: "06_rj_hooks.png", route: JOURNEY_BOOK, theme: "light" });
      await metric.selectOption({ index: 0 }).catch(() => undefined);
      await shot(page, { id: "06-11", file: "06_rj_pace.png", route: JOURNEY_BOOK, theme: "light" });
    }

    const exportBtn = page.getByTestId("journey-export-png");
    if (await exportBtn.count()) {
      await shot(page, { id: "06-16", file: "06_rj_export.png", route: JOURNEY_BOOK, theme: "light" });
    }

    await shot(page, { id: "06-12", file: "06_rj_fullpage.png", route: JOURNEY_BOOK, theme: "light", fullPage: true });

    const detailEmpty = page.getByTestId("journey-detail-empty");
    if (await detailEmpty.count()) {
      await shot(page, { id: "06-15", file: "06_rj_no_detail.png", route: JOURNEY_BOOK, theme: "light" });
    }
  });

  test("empty journey detail", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded", journey: "empty" });
    await gotoReady(page, JOURNEY_BOOK);
    await shot(page, { id: "06-04", file: "06_rj_empty_detail.png", route: JOURNEY_BOOK, theme: "light" });
  });
});
