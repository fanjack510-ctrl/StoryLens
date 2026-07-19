import { expect, test } from "@playwright/test";
import {
  buildChapterParagraphs,
  buildScenes,
  buildVisualizationFixture,
} from "./fixtures/readerJourneyE2eFixtures";

const localProvider = {
  capability_schema_version: "1c-a-2",
  enabled: true,
  name: "local_qwen14",
  default_model: "local-fake",
  configured: true,
  connected: true,
  healthy: true,
  allow_auto_route: true,
  automatic_route_eligible: true,
  eligible_for_automatic_analysis: true,
  manual_boundary_candidate_eligible: false,
  manual_selection_blockers: ["local_mode"],
  automatic_route_blockers: [],
  manual_short_task_eligible: true,
  supports_boundary_candidates: false,
  requires_boundary_review: false,
  automatic_boundary_routing: true,
  eligibility_status: "eligible",
  evaluated_at: "2026-01-01T00:00:00Z",
  health_state: "healthy",
  health_source: "configured_readiness",
  health_checked_at: "2026-01-01T00:00:00Z",
  provider_state_version: "state-local-1",
  capabilities: {
    cloud: false,
    enabled: true,
    default: true,
    manual_only: false,
    structured_output_mode: "json_object",
    sends_content_to_cloud: false,
    profile_name: "local",
    supports_boundary_candidates: false,
    requires_boundary_review: false,
    automatic_boundary_routing: true,
  },
  workflow_prompts: {
    boundary_candidate: "v3.5",
    boundary_adjudication: "v1",
    scene_analysis: "v3.1",
    thinking: false,
    boundary_confirmation: "none",
  },
};

function baseBookRoutes() {
  return {
    book: {
      id: 1,
      title: "Fixture Novel",
      source_file_name: "fixture.txt",
      source_file_hash: "deadbeef",
      created_at: "2026-01-01T00:00:00Z",
    },
    chapters: [
      {
        id: 2,
        book_id: 1,
        chapter_index: 1,
        section_type: "chapter",
        title: "第一章",
        display_title: "第一章",
      },
    ],
    paragraphs: {
      items: [
        {
          id: "B0001-C0002-P0001",
          raw_text: "开篇第一段。",
          paragraph_index: 1,
        },
        {
          id: "B0001-C0002-P0014",
          raw_text: "第十四段正文。",
          paragraph_index: 14,
        },
      ],
      total: 2,
      offset: 0,
      limit: 200,
      has_more: false,
    },
  };
}

const sceneResults = {
  run: {
    id: 77,
    status: "succeeded",
    provider: "local_qwen14",
    model: "local-fake",
    created_at: "2026-01-01T00:00:00Z",
  },
  chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
  boundary_revision: null,
  summary: {
    total_scene_count: 2,
    single_paragraph_scene_count: 0,
    longest_scene_ordinal: 1,
    longest_scene_paragraph_count: 1,
  },
  scenes: [
    {
      scene: {
        id: 101,
        ordinal: 1,
        scene_key: "S01",
        start_paragraph_id: "B0001-C0002-P0001",
        end_paragraph_id: "B0001-C0002-P0001",
        is_single_paragraph: true,
      },
      fields: {
        goal: { summary: "目标", evidence_paragraph_ids: ["B0001-C0002-P0001"] },
      },
      evidence: {
        goal: [{ paragraph_id: "B0001-C0002-P0001", quote: "开篇" }],
      },
    },
    {
      scene: {
        id: 114,
        ordinal: 14,
        scene_key: "S14",
        start_paragraph_id: "B0001-C0002-P0014",
        end_paragraph_id: "B0001-C0002-P0014",
        is_single_paragraph: true,
      },
      fields: {
        goal: { summary: "目标十四", evidence_paragraph_ids: ["B0001-C0002-P0014"] },
      },
      evidence: {
        goal: [{ paragraph_id: "B0001-C0002-P0014", quote: "十四" }],
      },
    },
  ],
};

test.describe("Phase 1C-C.2.3C current-page result composition", () => {
  test("E2E A: succeeded run auto-embeds results on /books", async ({ page }) => {
    let createCount = 0;
    let runStatus = "scene_analysis_running";
    let completed = 2;
    let createJourneyCount = 0;
    const fixture = baseBookRoutes();

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();

      if (url.includes("/health")) {
        return route.fulfill({
          json: { status: "ok", database: "ok", default_provider: "local_qwen14" },
        });
      }
      if (url.match(/\/books\/?\d*$/) && method === "GET" && !url.includes("chapters")) {
        if (url.endsWith("/books") || url.endsWith("/books/")) {
          return route.fulfill({ json: [fixture.book] });
        }
        return route.fulfill({ json: fixture.book });
      }
      if (url.includes("/chapters") && !url.includes("paragraphs") && !url.includes("analysis-runs")) {
        return route.fulfill({ json: fixture.chapters });
      }
      if (url.match(/\/scenes\/\d+\/paragraphs/)) {
        return route.fulfill({
          json: {
            paragraphs: [
              {
                id: "B0001-C0002-P0001",
                raw_text: "开篇第一段。",
                in_scene: true,
                paragraph_index: 1,
              },
            ],
          },
        });
      }
      if (url.includes("/paragraphs")) {
        return route.fulfill({ json: fixture.paragraphs });
      }
      if (url.includes("/model-providers")) {
        return route.fulfill({ json: [localProvider] });
      }
      if (url.match(/\/chapters\/\d+\/analysis-runs$/) && method === "POST") {
        createCount += 1;
        runStatus = "scene_analysis_running";
        completed = 2;
        return route.fulfill({ status: 202, json: { run_id: 77 } });
      }
      if (url.match(/\/analysis-runs\/77$/) && method === "GET") {
        if (runStatus === "scene_analysis_running") {
          completed = Math.min(14, completed + 6);
          if (completed >= 14) runStatus = "succeeded";
        }
        return route.fulfill({
          json: {
            id: 77,
            subject_id: "2",
            provider: "local_qwen14",
            model: "local-fake",
            status: runStatus,
            progress_current: completed,
            progress_total: 14,
            execution_mode: "local",
            cloud_consent: false,
            sends_content_to_cloud: false,
            retryable: false,
            created_at: "2026-01-01T00:00:00Z",
            started_at: "2026-01-01T00:00:01Z",
            completed_at: runStatus === "succeeded" ? "2026-01-01T00:05:00Z" : null,
            reusable_checkpoint_count: 0,
            conflicted_checkpoint_count: 0,
            checkpoint_total_count: 0,
            checkpoint_available: false,
            completed_scene_count: completed,
            total_scene_count: 14,
            scene_analysis_coverage_rate: completed / 14,
          },
        });
      }
      if (url.includes("/analysis-runs/77/reader-journey") && method === "POST") {
        createJourneyCount += 1;
        return route.fulfill({ status: 202, json: { journey_run_id: 9 } });
      }
      if (url.includes("/analysis-runs/77/reader-journey")) {
        return route.fulfill({ json: { status: "missing", visualization: null } });
      }
      if (url.includes("/analysis-runs/77/results")) {
        return route.fulfill({ json: { ...sceneResults, run: { ...sceneResults.run, id: 77 } } });
      }
      if (url.includes("/analysis-runs") && method === "GET") {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/scenes")) return route.fulfill({ json: [] });
      return route.fulfill({ status: 200, json: {} });
    });

    await page.goto("/books/1");
    await expect(page.getByTestId("book-chapter-shell")).toBeVisible();
    await page.getByTestId("shell-start-analysis").click();
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await page.getByLabel("执行模式").selectOption("local");
    await page.getByLabel("Provider").selectOption("local_qwen14");
    await page.getByTestId("start-analysis-submit").click();

    await expect(page).toHaveURL(/\/books\/1/);
    await expect(page).toHaveURL(/analysisRun=77/);
    await expect(page).not.toHaveURL(/\/tasks/);
    await expect(page.getByTestId("chapter-analysis-progress")).toBeVisible();

    await expect(page.getByTestId("embedded-analysis-result")).toBeVisible({ timeout: 20000 });
    await expect(page).toHaveURL(/view=result/);
    await expect(page).toHaveURL(/\/books\/1/);
    await expect(page).not.toHaveURL(/\/analysis-runs\/77\/results/);
    await expect(page.getByTestId("chapter-analysis-progress")).toHaveCount(0);
    await expect(page.getByTestId("scene-list")).toBeVisible();

    await page.getByTestId("scene-list-item-1").click();
    await expect(page.locator("#result-p-B0001-C0002-P0001")).toBeVisible();

    await page.getByTestId("book-view-reading").click();
    await expect(page.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "reading");
    await expect(page.getByTestId("chapter-analysis-complete-banner")).toBeVisible();
    await page.getByTestId("book-view-result").click();
    await expect(page.getByTestId("embedded-analysis-result")).toBeVisible();
    await expect(page).not.toHaveURL(/\/tasks/);
    await expect(page).not.toHaveURL(/\/analysis-runs\/77\/results/);
    expect(createCount).toBe(1);
    expect(createJourneyCount).toBe(0);
  });

  test("E2E B: deep-link restores Reader Journey sync workspace", async ({ page }) => {
    let createJourneyCount = 0;
    const fixture = baseBookRoutes();
    const visualization = buildVisualizationFixture();
    const scenes = buildScenes();
    const chapterParagraphs = buildChapterParagraphs();

    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok", database: "ok", default_provider: "fake" } });
      }
      if (url.match(/\/books\/1$/) && method === "GET") {
        return route.fulfill({ json: fixture.book });
      }
      if (url.includes("/chapters") && !url.includes("analysis-runs") && !url.includes("paragraphs")) {
        return route.fulfill({ json: fixture.chapters });
      }
      if (url.includes("/chapters/") && url.includes("/paragraphs")) {
        return route.fulfill({
          json: {
            items: chapterParagraphs,
            offset: 0,
            limit: 500,
            total: chapterParagraphs.length,
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
        createJourneyCount += 1;
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
            chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
            boundary_revision: null,
            summary: {
              total_scene_count: 14,
              single_paragraph_scene_count: 0,
              longest_scene_ordinal: 9,
              longest_scene_paragraph_count: 16,
            },
            scenes,
          },
        });
      }
      if (url.match(/\/scenes\/\d+\/paragraphs/)) {
        return route.fulfill({
          json: {
            paragraphs: [
              {
                id: "B0001-C0002-P0064",
                raw_text: "第十四景段落。",
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
      if (url.includes("/model-providers")) return route.fulfill({ json: [localProvider] });
      return route.fulfill({ json: {} });
    });

    await page.goto(
      "/books/1?chapter=2&analysisRun=55&view=result&resultTab=reader-journey&mode=sync&scene=14",
    );
    await expect(page.getByTestId("embedded-analysis-result")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page).toHaveURL(/scene=14/);
    await expect(page).toHaveURL(/mode=sync/);
    await expect(page).toHaveURL(/\/books\/1/);
    await expect(page.getByTestId("structured-chapter-text-pane")).toBeVisible();
    expect(createJourneyCount).toBe(0);

    await page.reload();
    await expect(page.getByTestId("journey-sync-workspace")).toBeVisible({ timeout: 15000 });
    await expect(page).toHaveURL(/scene=14/);
    expect(createJourneyCount).toBe(0);
  });

  test("E2E C: independent results route still works", async ({ page }) => {
    const fixture = baseBookRoutes();
    await page.route("**/api/v1/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/health")) {
        return route.fulfill({ json: { status: "ok", database: "ok", default_provider: "fake" } });
      }
      if (url.includes("/analysis-runs/55/results")) {
        return route.fulfill({
          json: { ...sceneResults, run: { ...sceneResults.run, id: 55 } },
        });
      }
      if (url.includes("/analysis-runs/55/reader-journey")) {
        return route.fulfill({ json: { status: "missing", visualization: null } });
      }
      if (url.match(/\/analysis-runs\/55$/)) {
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
      if (url.match(/\/scenes\/\d+\/paragraphs/)) {
        return route.fulfill({
          json: {
            paragraphs: [
              {
                id: "B0001-C0002-P0001",
                raw_text: "开篇第一段。",
                in_scene: true,
                paragraph_index: 1,
              },
            ],
          },
        });
      }
      if (url.includes("/books")) return route.fulfill({ json: fixture.book });
      if (url.includes("/chapters")) return route.fulfill({ json: fixture.chapters });
      return route.fulfill({ json: {} });
    });

    await page.goto("/analysis-runs/55/results");
    await expect(page.getByTestId("scene-list")).toBeVisible({ timeout: 15000 });
    await expect(page).toHaveURL(/\/analysis-runs\/55\/results/);
    await expect(page.getByTestId("scene-list-item-1")).toBeVisible();
  });
});
