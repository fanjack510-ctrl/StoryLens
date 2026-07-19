import { expect, test, type Route } from "@playwright/test";

function unhandledApi(route: Route, url: string) {
  return route.fulfill({
    status: 500,
    contentType: "application/json",
    body: JSON.stringify({
      error_code: "UNHANDLED_E2E_API_REQUEST",
      message: `Unhandled E2E API request: ${url}`,
      url,
    }),
  });
}

test("semantic conflict remains reviewable and can be rejected", async ({ page }) => {
  let userDecision = "pending";
  let confirmCalls = 0;
  const paragraphs = Array.from({ length: 5 }, (_, index) => ({
    id: `P${index + 1}`,
    chapter_id: 2,
    paragraph_index: index + 1,
    raw_text: `原创E2E段落${index + 1}`,
  }));
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const json = (body: unknown) => route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    if (
      url.includes("/books/1/chapters/2/boundary-review")
      && method === "GET"
    ) return json({
      id: 7, book_id: 1, chapter_id: 2, analysis_run_id: 54,
      prompt_version: "v3.5", provider: "fake_provider", model: "fake-model",
      status: "pending", candidate_count: 1,
      accepted_count: 0, rejected_count: userDecision === "reject" ? 1 : 0,
      manually_added_count: 0, created_at: new Date().toISOString(),
      completed_at: null, paragraphs,
      decisions: [{
        id: 1, transition_id: "T0017", left_paragraph_id: "P3",
        right_paragraph_id: "P4", model_candidate: true,
        model_boundary_candidate: true, model_confidence: 0.82,
        model_reason_code: null,
        first_pass_json: "{}",
        adjudication_result: null,
        review_priority: "high",
        user_decision: userDecision,
        user_reason: null,
        final_boundary: false,
        semantic_conflict: true,
        conflict_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
        deterministic_legal: false,
        deterministic_reason: null,
        enum_snapshot_json: JSON.stringify({
          goal_relation: "refined",
          action_chain_relation: "continuous",
          trigger_type: "object",
        }),
        source_batch_index: 3,
      }],
    });
    if (/\/books\/1$/.test(url)) return json({
      id: 1, title: "原创测试书", source_file_name: "fake.txt",
      source_file_hash: "a", created_at: new Date().toISOString(), revision_number: 1,
    });
    if (url.includes("/books/1/chapters")) return json([{
      id: 2, book_id: 1, chapter_index: 1, title: "第一章",
      display_title: "第一章", section_type: "chapter", word_count: 100,
    }]);
    if (url.includes("/chapters/2/paragraphs")) return json({
      items: paragraphs, offset: 0, limit: 200, total: 5, has_more: false,
    });
    if (url.includes("/chapters/2/scenes")) return json([]);
    if (url.includes("/decisions/T0017") && method === "PUT") {
      userDecision = JSON.parse(route.request().postData() || "{}").user_decision;
      return json({});
    }
    if (url.includes("/scene-preview")) return json({
      review_id: 7, coverage_rate: 1, scenes: [{ ordinal: 1 }],
    });
    if (url.includes("/scene-analysis-preflight")) return json({
      scene_count: 1, expected_request_count: 1, worst_case_request_count: 2,
      estimated_total_tokens: 100, worst_case_total_tokens: 200,
      estimated_cost: 0.01, worst_case_cost: 0.02, within_budget: true,
      exceeded_dimensions: [], remaining: { requests: 10, tokens: 10000, estimated_cost: 1 },
    });
    if (url.includes("/boundary-reviews/7/confirm") && method === "POST") {
      confirmCalls += 1;
      return json({
        revision_id: 1, revision_number: 1, scene_count: 1,
        coverage_rate: 1, run_status: "scene_analysis_running",
        scene_analysis_started: true, budget_blocked: false, stage: "scene_analysis",
      });
    }
    return unhandledApi(route, url);
  });
  await page.goto("/books/1");
  await page.getByTestId("book-more-menu-trigger").click();
  await page.getByTestId("book-more-boundary-review").click();
  await expect(page.getByTestId("semantic-conflict")).toContainText("T0017");
  await page.getByText("拒绝边界").click();
  await expect.poll(() => userDecision).toBe("reject");
  await page.getByText("全部确认").click();
  await expect(page.getByTestId("review-message")).toContainText("本章边界已确认");
  expect(confirmCalls).toBe(1);
});

test("partial run continues once from reusable checkpoints", async ({ page }) => {
  let preflightCalls = 0;
  let continueCalls = 0;
  const failedRun54 = {
    id: 54,
    book_id: 1,
    chapter_id: 2,
    subject_id: "2",
    subject_type: "chapter",
    provider: "aliyun_qwen_plus",
    provider_name: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    model_name: "qwen3.7-plus",
    status: "failed",
    progress_current: 0,
    progress_total: 1,
    execution_mode: "cloud",
    analysis_mode: "assisted_boundary_review",
    cloud_consent: true,
    sends_content_to_cloud: true,
    error_code: "SCENE_PIPELINE_FAILED",
    root_error_code: "BUSINESS_VALIDATION_FAILED",
    root_error_message: "candidate decision conflicts with deterministic enum rules",
    failed_stage: "business_validation",
    actual_failed_stage: "business_validation",
    failed_invocation_id: 96,
    failed_batch_index: 3,
    failed_transition_id: "T0017",
    validation_error_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
    retryable: false,
    user_action_hint: "从已有结果继续",
    created_at: new Date().toISOString(),
    checkpoint_available: true,
    detection_recovery_available: true,
    remaining_detection_batch_count: 7,
    reusable_checkpoint_count: 3,
    reusable_batch_count: 3,
    conflicted_checkpoint_count: 1,
    checkpoint_total_count: 10,
    total_detection_batch_count: 10,
    scene_analysis_resume_available: false,
    reservation_status: "released",
    recovery_preflight: {
      reused_batch_count: 3,
      remaining_batch_count: 7,
      expected_requests: 8,
      worst_case_requests: 16,
      estimated_tokens: 10384,
      worst_case_tokens: 25565,
      estimated_cost: 0.057632,
      worst_case_cost: 0.171994,
      currency: "CNY",
      remaining_budget: { requests: 145, tokens: 190562, estimated_cost: 4.97 },
      within_budget: true,
      exceeded_dimensions: [],
      requires_cloud_consent: true,
    },
  };
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const json = (body: unknown, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    if (/\/analysis-runs$/.test(url)) {
      // After recovery creation, list includes the new run.
      if (continueCalls > 0) {
        return json([
          {
            id: 61, subject_id: "2", provider: "fake_provider", model: "fake-model",
            status: "boundary_candidates_running", progress_current: 2, progress_total: 10,
            execution_mode: "cloud", cloud_consent: true, sends_content_to_cloud: true,
            recovered_from_run_id: 54, created_at: new Date().toISOString(),
          },
          failedRun54,
        ]);
      }
      return json([failedRun54]);
    }
    if (/\/analysis-runs\/54$/.test(url)) return json(failedRun54);
    if (url.includes("/model-invocations")) return json([]);
    if (url.includes("/recovery-preflight") && !url.includes("/recover/preflight")) {
      return json({
        recovered_batch_count: 3, total_detection_batch_count: 10,
        remaining_detection_batch_count: 7, semantic_conflict_count: 1,
        expected_request_count: 8, worst_case_request_count: 16,
        estimated_total_tokens: 10384, worst_case_total_tokens: 25565,
        estimated_cost: 0.057632, worst_case_cost: 0.171994, currency: "CNY",
        remaining: { requests: 145, tokens: 190562, estimated_cost: 4.97 },
        within_budget: true, exceeded_dimensions: [], requires_cloud_consent: true,
      });
    }
    if (url.includes("/recover/preflight")) {
      preflightCalls += 1;
      return json({
        source_run_id: 54,
        provider_name: "aliyun_qwen_plus",
        eligible: true,
        blockers: [],
        provider_state_version: "e2e-state-v1",
        capability_schema_version: "1c-a-2",
        health_state: "healthy",
        health_source: "cached_connection_test",
        reused_batch_count: 3,
        remaining_batch_count: 7,
        expected_requests: 8,
        worst_case_requests: 16,
        estimated_tokens: 10384,
        worst_case_tokens: 25565,
        estimated_cost: 0.057632,
        worst_case_cost: 0.171994,
        currency: "CNY",
        remaining_budget: { requests: 145, tokens: 190562, estimated_cost: 4.97 },
        within_budget: true,
        exceeded_dimensions: [],
        requires_cloud_consent: true,
      });
    }
    if (url.includes("/recover") || url.includes("/continue-from-checkpoints")) {
      continueCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 200));
      return json({
        run_id: 61,
        recovered_from_run_id: 54,
        status: "boundary_candidates_running",
        reused_batch_count: 3,
        remaining_batch_count: 7,
        reservation_id: 12,
        request_id: "e2e-recover",
      }, 202);
    }
    return unhandledApi(route, url);
  });
  await page.goto("/tasks");
  await page.getByText("查看详情").click();
  await expect(page.getByTestId("checkpoint-summary")).toContainText("3/10");
  await page.getByText("我同意新恢复任务按剩余批次发送必要正文到云端").click();
  const button = page.getByTestId("continue-from-checkpoints");
  await button.dblclick();
  await expect.poll(() => preflightCalls).toBe(1);
  await expect.poll(() => continueCalls).toBe(1);
  await expect(page.getByTestId("recovery-created")).toContainText("Run ID：61");
  await expect(page.getByTestId("recovery-highlight")).toContainText("61");
});
