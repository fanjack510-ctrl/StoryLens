import { expect, test } from "@playwright/test";

test("reader journey offline replay path (mocked)", async ({ page }) => {
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
              id: 1,
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
      body: JSON.stringify({ paragraphs: [{ id: "B0001-C0002-P0001", raw_text: "段", in_scene: true }] }),
    });
  });

  await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ journey_run_id: 902, status: "failed" }),
    });
  });

  await page.route("**/reader-journey-runs/902/progress", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        journey_run_id: 902,
        analysis_run_id: 55,
        status: "failed",
        total_scene_count: 14,
        completed_scene_count: 0,
        remaining_scene_count: 14,
        phase_count: 0,
        has_chapter_summary: false,
        retryable: false,
        root_error_code: "JOURNEY_QUESTION_CHAIN_INVALID",
        user_error_message: "旧版契约",
        offline_replay_available: true,
        offline_replayable_scene_count: 1,
        offline_replayable_invocation_ids: [134],
        current_contract_version: "1.2",
        blind_resume_blocked: true,
        resume_block_reason: "offline_replay_required",
        recovery_safe: false,
        reservation_released: true,
      }),
    });
  });

  await page.route("**/reader-journey-runs/902/scene-profiles/offline-replay", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        journey_run_id: 902,
        replayed_scene_ids: [1],
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

  await page.goto("/analysis-runs/55/results");
  await page.getByTestId("result-view-journey").click();
  await expect(page.getByTestId("journey-old-contract-notice")).toBeVisible();
  await expect(page.getByTestId("resume-reader-journey")).toBeDisabled();
  await page.getByTestId("offline-replay-reader-journey").click();
  await expect(page.getByTestId("journey-offline-replay-success")).toContainText("离线重放成功");
});
