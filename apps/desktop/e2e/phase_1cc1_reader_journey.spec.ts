import { expect, test } from "@playwright/test";

/** Phase 1C-C.1 Reader Journey — mocked API, no real Aliyun. */

test.describe("Phase 1C-C.1 Reader Journey", () => {
  test("generate reader journey from Run #55 results page", async ({ page }) => {
    const run55 = { id: 55, status: "succeeded", provider: "fake", model: "fake" };
    const preflight = {
      analysis_run_id: 55,
      total_scenes: 14,
      remaining_scenes: 14,
      scene_batch_count: 4,
      expected_requests: 5,
      worst_case_requests: 10,
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
    };
    const journeyResult = {
      journey_run_id: 901,
      analysis_run_id: 55,
      status: "succeeded",
      formula_version: "1.0",
      one_sentence_diagnosis: "章节以身份悬念驱动阅读",
      phases: Array.from({ length: 5 }, (_, i) => ({
        ordinal: i + 1,
        title: `阶段${i + 1}`,
        start_scene_ordinal: i * 3 + 1,
        end_scene_ordinal: Math.min((i + 1) * 3, 14),
        primary_reader_question: `问题${i + 1}`,
        summary: `阶段${i + 1}摘要`,
      })),
      scene_profiles: Array.from({ length: 14 }, (_, i) => ({
        scene_id: 6 + i,
        scene_ordinal: i + 1,
        scene_value_summary: `价值${i + 1}`,
        dominant_emotion: "好奇",
        engagement: { engagement_score: 50 + i },
        reader_question_in: [`入${i + 1}`],
        reader_question_out: [`出${i + 1}`],
        payoffs: [`回报${i + 1}`],
        hooks: [`钩子${i + 1}`],
        risk_points: [`风险${i + 1}`],
        evidence_paragraph_ids: [`B0001-C0002-P${String(i + 1).padStart(4, "0")}`],
      })),
    };

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
    await page.route("**/api/v1/analysis-runs/55/reader-journey", async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({ json: journeyResult });
        return;
      }
      await route.fulfill({ status: 202, json: { journey_run_id: 901, status: "queued" } });
    });
    await page.route("**/reader-journey-runs/901/progress", async (route) => {
      await route.fulfill({
        json: {
          journey_run_id: 901,
          analysis_run_id: 55,
          status: "succeeded",
          total_scene_count: 14,
          completed_scene_count: 14,
          remaining_scene_count: 0,
          completed_scene_ids: [],
          remaining_scene_ids: [],
          phase_count: 5,
          has_chapter_summary: true,
          retryable: false,
        },
      });
    });
    await page.route("**/reader-journey-runs/901/export**", async (route) => {
      await route.fulfill({ json: journeyResult });
    });
    await page.route("**/scenes/*/paragraphs", async (route) => {
      await route.fulfill({ json: { paragraphs: [] } });
    });

    await page.route("**/api/v1/analysis-runs/55/reader-journey/preflight", async (route) => {
      await route.fulfill({ json: preflight });
    });
    await page.goto("/analysis-runs/55/results");
    await page.getByTestId("result-view-journey").click();
    await page.getByTestId("generate-reader-journey").click();
    await expect(page.getByTestId("journey-preflight")).toBeVisible();
    await page.getByTestId("journey-cloud-consent").check();
    await page.getByTestId("start-reader-journey").click();
    await expect(page.getByTestId("journey-phases")).toContainText("阅读阶段（5）");
    await expect(page.getByTestId("journey-profiles")).toContainText("Scene Profile（14）");
    await page.getByTestId("results-more-menu-trigger").click();
    const [req] = await Promise.all([
      page.waitForRequest("**/reader-journey-runs/901/export**"),
      page.getByTestId("results-more-export-journey-json").click(),
    ]);
    expect(req.url()).toContain("format=json");
  });
});
