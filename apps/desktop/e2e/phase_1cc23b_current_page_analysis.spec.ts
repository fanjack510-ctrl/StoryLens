import { expect, test } from "@playwright/test";

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

test.describe("Phase 1C-C.2.3B current-page analysis progress", () => {
  test("create run stays on book page, polls progress, opens results", async ({ page }) => {
    let createCount = 0;
    let runStatus = "scene_analysis_running";
    let completed = 2;
    const pollTicks: number[] = [];

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
          return route.fulfill({
            json: [
              {
                id: 1,
                title: "Fixture Novel",
                source_file_name: "fixture.txt",
                source_file_hash: "deadbeef",
                created_at: "2026-01-01T00:00:00Z",
              },
            ],
          });
        }
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
      if (url.includes("/paragraphs")) {
        return route.fulfill({
          json: {
            items: [
              {
                id: "B0001-C0002-P0001",
                raw_text: "开篇第一段。",
                paragraph_index: 1,
              },
            ],
            total: 1,
            offset: 0,
            limit: 200,
            has_more: false,
          },
        });
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
        pollTicks.push(Date.now());
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
      if (url.includes("/analysis-runs/77/reader-journey")) {
        return route.fulfill({ json: { status: "missing", visualization: null } });
      }
      if (url.includes("/analysis-runs/77/results")) {
        return route.fulfill({
          json: {
            run: { id: 77, status: "succeeded", provider: "local_qwen14", model: "local-fake" },
            chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
            boundary_revision: null,
            summary: { total_scene_count: 14 },
            scenes: [],
          },
        });
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

    await expect(page).toHaveURL(/analysisRun=77/);
    await expect(page).not.toHaveURL(/\/tasks/);
    await expect(page.getByTestId("chapter-analysis-progress")).toBeVisible();
    expect(createCount).toBe(1);

    // Phase 1C-C.2.3C: succeeded runs auto-embed results on /books (no forced jump).
    await expect(page.getByTestId("embedded-analysis-result")).toBeVisible({ timeout: 20000 });
    await expect(page).toHaveURL(/\/books\/1/);
    await expect(page).toHaveURL(/view=result/);
    await expect(page).not.toHaveURL(/\/analysis-runs\/77\/results/);
    expect(createCount).toBe(1);
    expect(pollTicks.length).toBeGreaterThan(0);
  });

  test("failed/partial resume reuses same run id", async ({ page }) => {
    let resumeCount = 0;
    let status = "scene_analysis_partial";

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
      if (url.includes("/paragraphs")) {
        return route.fulfill({
          json: {
            items: [
              {
                id: "B0001-C0002-P0001",
                raw_text: "段落。",
                paragraph_index: 1,
              },
            ],
            total: 1,
            offset: 0,
            limit: 200,
            has_more: false,
          },
        });
      }
      if (url.includes("/chapters") && !url.includes("analysis-runs")) {
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
      if (url.match(/\/analysis-runs\/88$/) && method === "GET") {
        return route.fulfill({
          json: {
            id: 88,
            subject_id: "2",
            provider: "fake",
            model: "fake",
            status,
            progress_current: 4,
            progress_total: 14,
            execution_mode: "cloud",
            cloud_consent: true,
            sends_content_to_cloud: true,
            retryable: true,
            created_at: "2026-01-01T00:00:00Z",
            reusable_checkpoint_count: 0,
            conflicted_checkpoint_count: 0,
            checkpoint_total_count: 0,
            checkpoint_available: false,
            completed_scene_count: status === "succeeded" ? 14 : 4,
            total_scene_count: 14,
            remaining_scene_count: status === "succeeded" ? 0 : 10,
            scene_analysis_resume_available: status !== "succeeded",
            user_action_hint: "部分场景已完成，可继续恢复。",
          },
        });
      }
      if (url.includes("/resume-scene-analysis") && method === "POST" && !url.includes("preflight")) {
        resumeCount += 1;
        status = "succeeded";
        return route.fulfill({ json: { run_id: 88, status: "scene_analysis_running" } });
      }
      if (url.includes("/reader-journey")) {
        return route.fulfill({ json: { status: "missing", visualization: null } });
      }
      if (url.includes("/analysis-runs/88/results")) {
        return route.fulfill({
          json: {
            run: { id: 88, status: "succeeded", provider: "fake", model: "fake" },
            chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
            boundary_revision: null,
            summary: { total_scene_count: 14 },
            scenes: [],
          },
        });
      }
      if (url.includes("/analysis-runs") && method === "GET") {
        return route.fulfill({ json: [] });
      }
      if (url.includes("/scenes")) return route.fulfill({ json: [] });
      return route.fulfill({ json: {} });
    });

    await page.goto("/books/1?chapter=2&analysisRun=88");
    await expect(page.getByTestId("chapter-analysis-progress")).toBeVisible();
    await expect(page.getByTestId("chapter-analysis-failure")).toBeVisible();
    // Polling may remount the button; use DOM click for stability.
    await page.getByTestId("chapter-analysis-resume").evaluate((el) => (el as HTMLButtonElement).click());
    // Phase 1C-C.2.3C: succeeded auto-embeds results (progress success card is not kept visible).
    await expect(page.getByTestId("embedded-analysis-result")).toBeVisible({ timeout: 15000 });
    expect(resumeCount).toBe(1);
    await expect(page).toHaveURL(/analysisRun=88/);
    await expect(page).toHaveURL(/view=result/);
    await expect(page).not.toHaveURL(/\/tasks/);
  });
});
