import { expect, test } from "@playwright/test";

/**
 * Phase 1C-A.10 Fake-provider style UI contract for Scene Analysis resume card.
 * Does not call real Aliyun; mocks task detail payload in the page via route.
 */
test.describe("Phase 1C-A.10 Scene Analysis resume UI", () => {
  test("shows scene resume card and hides detection recovery", async ({ page }) => {
    const failedRun55 = {
      id: 55,
      subject_id: "2",
      provider: "aliyun_qwen_plus",
      model: "qwen3.7-plus",
      status: "failed",
      progress_current: 1,
      progress_total: 1,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      error_code: "SCENE_ANALYSIS_FAILED",
      root_error_code: "PROVIDER_DISABLED",
      root_error_message: "Provider已停用，拒绝发送请求",
      failed_stage: "scene_analysis",
      actual_failed_stage: "scene_analysis",
      failed_invocation_id: 106,
      failed_scene_id: 6,
      failed_scene_index: 1,
      retryable: false,
      created_at: new Date().toISOString(),
      checkpoint_available: false,
      detection_recovery_available: false,
      remaining_detection_batch_count: 0,
      scene_analysis_resume_available: true,
      boundary_revision_id: 1,
      total_scene_count: 14,
      completed_scene_count: 0,
      remaining_scene_count: 14,
      scene_analysis_coverage_rate: 1,
      reusable_checkpoint_count: 10,
      checkpoint_total_count: 10,
      reservation_status: "released",
      recovered_from_run_id: 54,
    };

    await page.route("**/api/v1/analysis-runs", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: [failedRun55] });
        return;
      }
      await route.continue();
    });
    await page.route("**/api/v1/analysis-runs/55", async (route) => {
      await route.fulfill({ json: failedRun55 });
    });
    await page.route("**/api/v1/analysis-runs/55/model-invocations", async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route(
      "**/api/v1/analysis-runs/55/resume-scene-analysis/preflight**",
      async (route) => {
        await route.fulfill({
          json: {
            run_id: 55,
            boundary_revision_id: 1,
            total_scene_count: 14,
            completed_scene_count: 0,
            remaining_scene_count: 14,
            remaining_scene_ids: [6],
            expected_requests: 14,
            worst_case_requests: 28,
            estimated_tokens: 40000,
            worst_case_tokens: 47788,
            estimated_cost: 0.2,
            worst_case_cost: 0.36,
            remaining_budget: { requests: 100, tokens: 100000, estimated_cost: 4 },
            within_budget: true,
            exceeded_dimensions: [],
            provider_state_version: "e2e-ver",
            provider_name: "aliyun_qwen_plus",
            eligible: true,
            blockers: [],
            requires_cloud_consent: true,
            estimated: true,
            currency: "CNY",
            coverage_rate: 1,
          },
        });
      },
    );

    await page.goto("/tasks");
    await page.getByText("查看详情").first().click();
    await expect(page.getByTestId("scene-analysis-resume-card")).toBeVisible();
    await expect(page.getByTestId("checkpoint-summary")).toHaveCount(0);
    await expect(page.getByTestId("scene-remaining-count")).toHaveText("14");
    await expect(page.getByTestId("continue-scene-analysis")).toBeDisabled();
    await page.getByRole("checkbox").check();
    await expect(page.getByTestId("continue-scene-analysis")).toBeEnabled();
  });
});
