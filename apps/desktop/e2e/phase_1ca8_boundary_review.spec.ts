import { expect, test } from "@playwright/test";

test("timeline yellow candidate selects T0017 and confirm blocks on pending", async ({ page }) => {
  let confirmCalls = 0;
  let decided: string | null = null;
  const paragraphs = Array.from({ length: 20 }, (_, i) => ({
    id: `P${i + 1}`,
    chapter_id: 2,
    paragraph_index: i + 1,
    raw_text: `段落${i + 1}`,
  }));

  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    const decisions = [
      {
        id: 11,
        transition_id: "M-B0001-C0002-P0012",
        left_paragraph_id: "P12",
        right_paragraph_id: "P13",
        model_candidate: false,
        model_confidence: 0,
        model_reason_code: null,
        first_pass_json: "{}",
        adjudication_result: "{}",
        review_priority: "high",
        user_decision: "manually_added",
        final_boundary: true,
      },
      {
        id: 2,
        transition_id: "T0017",
        left_paragraph_id: "P17",
        right_paragraph_id: "P18",
        model_candidate: true,
        model_confidence: 0.81,
        model_reason_code: "primary_goal_reset",
        first_pass_json: "{}",
        adjudication_result: "{}",
        review_priority: "high",
        user_decision: decided === "T0017" ? "reject" : "pending",
        semantic_conflict: true,
        conflict_code: "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
        deterministic_legal: false,
        deterministic_reason: null,
        model_boundary_candidate: true,
        source_batch_index: 3,
        enum_snapshot_json: JSON.stringify({
          goal_relation: "refined",
          action_chain_relation: "continuous",
        }),
      },
    ];

    if (url.includes("/books/1/chapters/2/boundary-review") && method === "GET") {
      return json({
        id: 1,
        book_id: 1,
        chapter_id: 2,
        analysis_run_id: 55,
        status: "in_review",
        provider: "fake_provider",
        model: "fake-model",
        prompt_version: "v3.5",
        accepted_count: decided === "T0017" ? 0 : 9,
        rejected_count: decided === "T0017" ? 1 : 0,
        manually_added_count: 1,
        paragraphs,
        decisions,
      });
    }
    if (/\/books\/1$/.test(url)) {
      return json({
        id: 1,
        title: "原创测试书",
        source_file_name: "fake.txt",
        source_file_hash: "a",
        created_at: new Date().toISOString(),
        revision_number: 1,
      });
    }
    if (url.includes("/books/1/chapters")) {
      return json([
        {
          id: 2,
          book_id: 1,
          chapter_index: 1,
          title: "第一章",
          display_title: "第一章",
          section_type: "chapter",
          word_count: 100,
        },
      ]);
    }
    if (url.includes("/chapters/2/paragraphs")) {
      return json({
        items: paragraphs,
        offset: 0,
        limit: 200,
        total: paragraphs.length,
        has_more: false,
      });
    }
    if (url.includes("/chapters/2/scenes")) return json([]);
    if (url.includes("/decisions/") && method === "PUT") {
      decided = "T0017";
      return json({
        id: 1,
        status: "in_review",
        provider: "fake_provider",
        model: "fake-model",
        prompt_version: "v3.5",
        accepted_count: 0,
        rejected_count: 1,
        manually_added_count: 1,
        paragraphs,
        decisions: decisions.map((item) =>
          item.transition_id === "T0017"
            ? { ...item, user_decision: "reject", final_boundary: false }
            : item,
        ),
      });
    }
    if (url.includes("/scene-preview")) {
      return json({
        coverage_rate: 1,
        scenes: Array.from({ length: 12 }, (_, i) => ({ ordinal: i + 1 })),
      });
    }
    if (url.includes("/scene-analysis-preflight")) {
      return json({
        scene_count: 12,
        expected_request_count: 12,
        worst_case_request_count: 24,
        estimated_total_tokens: 1000,
        worst_case_total_tokens: 2000,
        estimated_cost: 0.01,
        worst_case_cost: 0.02,
        within_budget: true,
        exceeded_dimensions: [],
        remaining: { requests: 50, tokens: 80000, estimated_cost: 2 },
      });
    }
    if (url.includes("/confirm") && method === "POST") {
      confirmCalls += 1;
      return json({
        revision_id: 7,
        revision_number: 1,
        scene_count: 12,
        scene_analysis_started: true,
        budget_blocked: false,
      });
    }
    return json({});
  });

  await page.goto("/books/1");
  await page.getByTestId("book-more-menu-trigger").click();
  await page.getByTestId("book-more-boundary-review").click();
  await expect(page.getByTestId("review-stats")).toContainText("待审 1");
  await page.getByTestId("timeline-T0017").click();
  await expect(page.getByTestId("decision-card-T0017")).toHaveClass(/selected/);
  await expect(page.getByTestId("semantic-conflict")).toContainText("T0017");
  await expect(page.getByTestId("semantic-conflict")).toContainText(
    "CANDIDATE_TRUE_WITHOUT_LEGAL_REASON",
  );

  await page.getByTestId("confirm-all-boundaries").click();
  await expect(page.getByTestId("review-message")).toContainText(
    "还有1个候选边界尚未处理",
  );
  expect(confirmCalls).toBe(0);

  await page.getByTestId("locate-next-pending").click();
  await expect(page.getByTestId("decision-card-T0017")).toHaveClass(/selected/);

  await page.getByRole("button", { name: "拒绝边界" }).click();
  await expect(page.getByTestId("review-message")).toContainText("已保存");
  await expect(page.getByTestId("review-stats")).toContainText("待审 0");

  await page.getByTestId("confirm-all-boundaries").click();
  await expect.poll(() => confirmCalls).toBe(1);
  await expect(page.getByTestId("review-message")).toContainText("Revision #7");
});
