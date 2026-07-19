import { expect, test } from "@playwright/test";

test("offline replay refreshes resume preflight and enables resume (mocked)", async ({ page }) => {
  let progressPhase: "failed" | "partial" = "failed";
  let createCalled = 0;
  let resumeCalled = 0;

  await page.route("**/api/v1/analysis-runs/55/results**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        run: { id: 55, status: "succeeded", provider: "fake", model: "fake" },
        chapter: { id: 2, title: "第1章", display_title: "第1章" },
        summary: { total_scene_count: 14, coverage_rate: 1, evidence_coverage_rate: 1 },
        boundary_revision: { revision_number: 1 },
        scenes: [
          {
            scene: {
              id: 6,
              ordinal: 1,
              scene_key: "S1",
              start_paragraph_id: "B0001-C0002-P0001",
              end_paragraph_id: "B0001-C0002-P0012",
            },
            analysis_artifact: {
              id: 1,
              provider: "fake",
              model: "fake",
              prompt_version: "v3.1",
              analysis: { goal: { summary: "g", evidence_paragraph_ids: [] } },
            },
            evidence: [],
          },
        ],
      }),
    });
  });

  await page.route("**/api/v1/scenes/**/paragraphs", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        paragraphs: [{ id: "B0001-C0002-P0001", raw_text: "段", in_scene: true }],
      }),
    });
  });

  await page.route("**/api/v1/analysis-runs/55/reader-journey/preflight**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        analysis_run_id: 55,
        total_scenes: 14,
        remaining_scenes: 14,
        scene_batch_count: 9,
        expected_requests: 10,
        worst_case_requests: 20,
        estimated_tokens: 12000,
        worst_case_tokens: 24000,
        estimated_cost: 0.1,
        worst_case_cost: 0.2,
        within_budget: true,
        exceeded_dimensions: [],
        provider_state_version: "test",
        provider_name: "fake",
        eligible: true,
        blockers: [],
        requires_cloud_consent: false,
        currency: "CNY",
        planner_version: "1.1",
        batch_plan: ["Scene 1单独", "Scene 2—3"],
      }),
    });
  });

  await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
    if (route.request().method() === "POST") {
      createCalled += 1;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          journey_run_id: 2,
          status: "scene_profiles_partial",
          existing_journey_run_id: 2,
          creation_blocked_reason: "ACTIVE_OR_RECOVERABLE_JOURNEY_EXISTS",
          recovery_recommended: true,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ journey_run_id: 2, status: progressPhase === "failed" ? "failed" : "scene_profiles_partial" }),
    });
  });

  await page.route("**/reader-journey-runs/2/progress", async (route) => {
    if (progressPhase === "failed") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          journey_run_id: 2,
          analysis_run_id: 55,
          status: "failed",
          total_scene_count: 14,
          completed_scene_count: 0,
          remaining_scene_count: 14,
          completed_scene_ids: [],
          remaining_scene_ids: [6, 7, 8],
          phase_count: 0,
          has_chapter_summary: false,
          retryable: false,
          root_error_code: "STRUCTURAL_VALIDATION_FAILED",
          offline_replay_available: true,
          offline_replayable_scene_count: 1,
          offline_replayable_invocation_ids: [134],
          current_contract_version: "1.2",
          blind_resume_blocked: true,
          resume_block_reason: "offline_replay_required",
          recovery_safe: false,
          planner_version: "1.1",
          scene_contract_version: "1.1",
          reservation_released: true,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        journey_run_id: 2,
        analysis_run_id: 55,
        status: "scene_profiles_partial",
        total_scene_count: 14,
        completed_scene_count: 1,
        remaining_scene_count: 13,
        completed_scene_ids: [6],
        remaining_scene_ids: [7, 8, 9],
        phase_count: 0,
        has_chapter_summary: false,
        retryable: true,
        offline_replay_available: false,
        offline_replayable_scene_count: 0,
        offline_replayable_invocation_ids: [],
        current_contract_version: "1.2",
        blind_resume_blocked: false,
        resume_block_reason: null,
        recovery_safe: true,
        planner_version: "1.1",
        scene_contract_version: "1.2",
        reservation_released: true,
        resume_preflight: {
          remaining_scenes: 13,
          scene_batch_count: 7,
          batch_plan: ["Scene 2—3", "Scene 4—5"],
          expected_requests: 8,
          worst_case_requests: 16,
          estimated_cost: 0.08,
          planner_version: "1.1",
          scene_contract_version: "1.2",
          currency: "CNY",
        },
      }),
    });
  });

  await page.route("**/reader-journey-runs/2/scene-profiles/offline-replay", async (route) => {
    progressPhase = "partial";
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        journey_run_id: 2,
        replayed_scene_ids: [6],
        completed_count: 1,
        remaining_count: 13,
        source_invocation_ids: [134],
        migrated_from_contract_version: "1.1",
        current_contract_version: "1.2",
        http_requests: 0,
        tokens: 0,
        cost: 0,
        idempotent_replay: false,
      }),
    });
  });

  await page.route("**/reader-journey-runs/2/resume", async (route) => {
    resumeCalled += 1;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ journey_run_id: 2, status: "scene_profiles_running" }),
    });
  });

  await page.goto("/analysis-runs/55/results");
  await page.getByTestId("result-view-journey").click();
  await expect(page.getByTestId("journey-old-contract-notice")).toBeVisible();
  await expect(page.getByTestId("generate-reader-journey")).toBeDisabled();
  await expect(page.getByTestId("generate-reader-journey")).toHaveText("请先恢复剩余任务");
  await expect(page.getByTestId("resume-reader-journey")).toBeDisabled();

  await page.getByTestId("offline-replay-reader-journey").click();
  await expect(page.getByTestId("journey-offline-replay-success")).toContainText("离线重放成功");
  await expect(page.getByTestId("journey-resume-preflight")).toBeVisible();
  await expect(page.getByTestId("journey-batch-plan")).not.toContainText("Scene 1单独");
  await expect(page.getByTestId("journey-resume-preflight")).toContainText("7");
  await expect(page.getByTestId("journey-resume-preflight")).toContainText("8");

  await page.getByTestId("journey-cloud-consent").check();
  const resume = page.getByTestId("resume-reader-journey");
  await expect(resume).toBeEnabled();
  await expect(resume).toHaveText("恢复剩余任务");

  // Do not auto-resume; only verify enablement. Zero cloud create beyond blocked replay.
  expect(createCalled).toBe(0);
  expect(resumeCalled).toBe(0);
});
