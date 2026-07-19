import { expect, test } from "@playwright/test";

/** Phase 1C-C.1.2 Reader Journey truncation UX — mocked API, no real Aliyun. */

test.describe("Phase 1C-C.1.2 Reader Journey truncation", () => {
  test("failed OUTPUT_TRUNCATED message, resume reuse, polling stop, blind resume blocked", async ({
    page,
  }) => {
    const run55 = { id: 55, status: "succeeded", provider: "fake", model: "fake" };
    const journeyRunId = 902;
    let progressPollCount = 0;

    const minimalScene = {
      scene: {
        id: 6,
        scene_key: "B0001-C0002-R0001-S0001",
        ordinal: 1,
        start_paragraph_id: "B0001-C0002-P0001",
        end_paragraph_id: "B0001-C0002-P0012",
        paragraph_count: 12,
        is_single_paragraph: false,
        boundary_source: "user_added",
        boundary_revision_id: 1,
        boundary_detected: true,
        boundary_confidence: 0.9,
      },
      analysis_artifact: {
        id: 9,
        schema_version: "v1",
        prompt_version: "v3.1",
        provider: "fake",
        model: "fake",
        confidence: 0.8,
        validation_status: "valid",
        created_at: "2026-07-17T07:00:00Z",
        offline_recovered: false,
        analysis: {
          scene_id: "B0001-C0002-R0001-S0001",
          entry_state: { summary: "进入-1", evidence_paragraph_ids: ["B0001-C0002-P0001"] },
          goal: { summary: "目标-1", evidence_paragraph_ids: ["B0001-C0002-P0001"] },
          obstacle: { summary: "", evidence_paragraph_ids: [] },
          key_actions: [{ summary: "动作-1", evidence_paragraph_ids: ["B0001-C0002-P0001"] }],
          turning_point: { summary: "", evidence_paragraph_ids: [] },
          outcome: { summary: "结果-1", evidence_paragraph_ids: ["B0001-C0002-P0012"] },
          unresolved_question: { summary: "", evidence_paragraph_ids: [] },
          function_tags: ["事件推进"],
          confidence: 0.8,
        },
      },
      evidence: [],
      illegal_evidence: [],
      revision: null,
    };

    await page.route("**/api/v1/analysis-runs/55/results", async (route) => {
      await route.fulfill({
        json: {
          run: run55,
          chapter: { id: 2, title: "第1章 戏鬼回家", display_title: "第1章 戏鬼回家" },
          boundary_revision: { id: 1, revision_number: 1, coverage_rate: 1 },
          summary: { total_scene_count: 14, evidence_coverage_rate: 1 },
          scenes: [minimalScene],
        },
      });
    });

    await page.route("**/api/v1/analysis-runs/55/reader-journey/preflight", async (route) => {
      await route.fulfill({
        json: {
          analysis_run_id: 55,
          total_scenes: 14,
          remaining_scenes: 14,
          scene_batch_count: 7,
          expected_requests: 8,
          worst_case_requests: 20,
          estimated_tokens: 12000,
          worst_case_tokens: 24000,
          estimated_cost: 0.1,
          worst_case_cost: 0.2,
          within_budget: true,
          exceeded_dimensions: [],
          provider_state_version: "e2e-rj",
          provider_name: "fake",
          eligible: true,
          blockers: [],
          requires_cloud_consent: false,
          currency: "CNY",
          stage1_scene_profiles: {},
          stage2_chapter_synthesis: {},
        },
      });
    });

    await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: null });
        return;
      }
      await route.fulfill({
        status: 202,
        json: {
          journey_run_id: journeyRunId,
          status: "failed",
          idempotent_replay: true,
          existing_journey_run_id: journeyRunId,
          creation_blocked_reason: "ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS",
        },
      });
    });

    await page.route("**/reader-journey-runs/902/progress", async (route) => {
      progressPollCount += 1;
      await route.fulfill({
        json: {
          journey_run_id: journeyRunId,
          analysis_run_id: 55,
          status: "failed",
          total_scene_count: 14,
          completed_scene_count: 0,
          remaining_scene_count: 14,
          completed_scene_ids: [],
          remaining_scene_ids: [],
          phase_count: 0,
          has_chapter_summary: false,
          retryable: false,
          root_error_code: "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
          root_error_message: "单个Scene的读者旅程Profile输出仍超过上限",
          user_error_message: "单个Scene的读者旅程Profile输出仍超过上限，无法继续拆批",
          blind_resume_blocked: true,
          resume_block_reason: "planner_outdated",
          recovery_safe: false,
          failed_stage: "reader_journey_scene_profiles",
          failed_scene_ordinal: 1,
          failed_scene_id: 6,
          failed_invocation_id: 501,
          request_count: 1,
          total_tokens: 800,
          estimated_cost: 0.01,
          currency: "CNY",
          reservation_released: true,
        },
      });
    });

    await page.route("**/reader-journey-runs/902/resume", async (route) => {
      await route.fulfill({
        status: 409,
        json: {
          detail: {
            error_code: "JOURNEY_SINGLE_PROFILE_OUTPUT_TRUNCATED",
            message: "当前失败态不支持盲目恢复；请升级批次规划/契约后按恢复预检重试",
          },
        },
      });
    });

    await page.route("**/scenes/*/paragraphs", async (route) => {
      await route.fulfill({ json: { paragraphs: [] } });
    });

    await page.goto("/analysis-runs/55/results");
    await page.getByTestId("result-view-journey").click();
    await page.getByTestId("generate-reader-journey").click();
    await expect(page.getByTestId("journey-preflight")).toBeVisible();
    await page.getByTestId("journey-cloud-consent").check();
    await page.getByTestId("start-reader-journey").click();

    await expect(page.getByTestId("journey-failed")).toBeVisible();
    await expect(page.getByTestId("journey-failed")).toContainText(
      "单个Scene的读者旅程Profile输出仍超过上限",
    );

    await page.waitForTimeout(4000);
    expect(progressPollCount).toBeLessThanOrEqual(2);

    const resumeButton = page.getByTestId("resume-reader-journey");
    await expect(resumeButton).toBeDisabled();
    await expect(resumeButton).toHaveText("请升级批次规划后恢复");
  });
});
