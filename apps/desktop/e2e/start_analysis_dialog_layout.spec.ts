import { test, expect } from "@playwright/test";

const plusProvider = {
  capability_schema_version: "1c-a-2",
  enabled: true,
  name: "aliyun_qwen_plus",
  default_model: "configured-plus",
  configured: true,
  connected: true,
  healthy: true,
  allow_auto_route: false,
  automatic_route_eligible: false,
  eligible_for_automatic_analysis: false,
  manual_boundary_candidate_eligible: true,
  manual_selection_blockers: [],
  automatic_route_blockers: ["auto_route_disabled"],
  manual_short_task_eligible: false,
  supports_boundary_candidates: true,
  requires_boundary_review: true,
  automatic_boundary_routing: false,
  eligibility_status: "eligible",
  evaluated_at: "2026-07-16T00:00:00Z",
  health_state: "healthy",
  health_source: "configured_readiness",
  health_checked_at: "2026-07-16T00:00:00Z",
  provider_state_version: "state-1",
  capabilities: {
    cloud: true,
    enabled: true,
    default: false,
    manual_only: false,
    structured_output_mode: "json_object",
    sends_content_to_cloud: true,
    profile_name: "plus",
    supports_boundary_candidates: true,
    requires_boundary_review: true,
    automatic_boundary_routing: false,
  },
  workflow_prompts: {
    boundary_candidate: "v3.5",
    boundary_adjudication: "v1",
    scene_analysis: "v3.1",
    thinking: false,
    boundary_confirmation: "human_required",
  },
};

const longBudget = {
  eligible: true,
  provider_state_version: "state-1",
  within_budget: true,
  exceeded_dimensions: [],
  stage: "boundary_review_generation",
  paragraph_count: 68,
  transition_count: 67,
  detection_batch_count: 10,
  adjudication_batch_count_estimated: 1,
  expected_request_count: 11,
  worst_case_request_count: 22,
  estimated_total_tokens: 14500,
  worst_case_total_tokens: 29109,
  estimated_cost: 0.09,
  worst_case_cost: 0.19,
  currency: "CNY",
  remaining: { requests: 70, tokens: 93011, estimated_cost: 2.676 },
  note: "本阶段不会执行Scene Analysis。" + "预览占位说明。".repeat(40),
};

async function mockApis(page: import("@playwright/test").Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/api/v1/books/1/chapters") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { id: 7, title: "第一章", section_type: "chapter", chapter_index: 1 },
        ]),
      });
    }
    if (url.match(/\/api\/v1\/books\/1\/?$/) && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: 1, title: "布局测试书", author: "test" }),
      });
    }
    if (url.includes("/api/v1/chapters/7/paragraphs")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [{ paragraph_id: "p1", text: "段落一", offset: 0 }],
          total: 1,
          offset: 0,
          limit: 200,
        }),
      });
    }
    if (url.includes("/api/v1/chapters/7/scenes")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    }
    if (url.includes("/api/v1/model-providers") && method === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([plusProvider]),
      });
    }
    if (url.includes("/api/v1/analysis-runs/preflight") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(longBudget),
      });
    }
    if (url.includes("/analysis-runs") && method === "POST") {
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error_code: "E2E_BLOCKED",
          message: "e2e must not create runs",
        }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
}

test.describe("StartAnalysisDialog layout", () => {
  test.use({ viewport: { width: 1280, height: 720 } });

  test("小视口下 Body 可滚动且创建任务按钮在视口内", async ({ page }) => {
    await mockApis(page);
    await page.goto("/books/1");
    await expect(page.getByTestId("shell-start-analysis")).toBeEnabled();
    await page.getByTestId("shell-start-analysis").click();

    const dialog = page.getByTestId("start-analysis-dialog");
    await expect(dialog).toBeVisible();
    await page.getByLabel("执行模式").selectOption("cloud");
    await page.getByLabel("Provider").selectOption("aliyun_qwen_plus");
    await page.getByRole("checkbox").check();

    const preview = page.getByTestId("stage1-budget-preview");
    await expect(preview).toBeVisible();
    await expect(preview).toContainText("不会执行Scene Analysis");

    const body = page.getByTestId("start-analysis-modal-body");
    const scrollable = await body.evaluate((el) => el.scrollHeight > el.clientHeight || getComputedStyle(el).overflowY === "auto");
    expect(scrollable).toBeTruthy();

    const submit = page.getByTestId("start-analysis-submit");
    await expect(submit).toBeVisible();
    const inViewport = await submit.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      return rect.top >= 0 && rect.bottom <= window.innerHeight && rect.left >= 0 && rect.right <= window.innerWidth;
    });
    expect(inViewport).toBeTruthy();

    await expect(page.getByTestId("start-analysis-modal-footer")).toBeVisible();
    // Do not click 创建任务 — no real Aliyun / run creation.
  });
});
