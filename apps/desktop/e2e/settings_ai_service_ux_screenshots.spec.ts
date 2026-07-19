import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";

const OUT = "d:/Dstorylens/audits/single-chapter-pipeline/ui-changes/screenshots";

const budget = {
  cloud_request_budget_enabled: true,
  cloud_max_input_tokens_per_request: 16000,
  cloud_max_output_tokens_per_request: 2000,
  cloud_max_requests_per_run: 10,
  cloud_daily_request_limit: 30,
  cloud_daily_token_limit: 200000,
  cloud_daily_estimated_cost_limit: 5,
  currency: "CNY",
  cloud_stop_on_unknown_pricing: true,
  cloud_confirm_each_paid_test: true,
};

function connectedProvider() {
  return {
    capability_schema_version: "1c-a-2",
    name: "aliyun_qwen_plus",
    default_model: "qwen3.7-plus",
    enabled: true,
    healthy: true,
    configured: true,
    connected: true,
    status: "ready",
    eligible_for_automatic_analysis: false,
    supports_boundary_candidates: true,
    requires_boundary_review: true,
    automatic_boundary_routing: false,
    manual_boundary_candidate_eligible: true,
    automatic_route_eligible: false,
    manual_short_task_eligible: false,
    manual_selection_blockers: [],
    automatic_route_blockers: ["auto_route_disabled"],
    allow_auto_route: false,
    eligibility_status: "eligible",
    evaluated_at: "2026-07-19T00:00:00Z",
    health_state: "healthy",
    health_source: "configured_readiness",
    health_checked_at: "2026-07-19T00:00:00Z",
    provider_state_version: "state-1",
    capabilities: {
      enabled: true,
      cloud: true,
      region: "cn-beijing",
      default: false,
      manual_only: false,
      structured_output_mode: "json_object",
      sends_content_to_cloud: true,
      profile_name: "aliyun_qwen_plus",
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
}

function disconnectedProvider() {
  return {
    ...connectedProvider(),
    configured: false,
    connected: false,
    healthy: false,
    enabled: false,
    health_state: "unhealthy",
    manual_boundary_candidate_eligible: false,
    manual_selection_blockers: ["provider_not_configured", "credential_missing"],
    eligibility_status: "blocked",
  };
}

async function mockApis(
  page: Page,
  opts: { connected: boolean; cloudEnabled: boolean },
) {
  const provider = opts.connected ? connectedProvider() : disconnectedProvider();
  await page.unroute("**/api/v1/**").catch(() => undefined);
  await page.unroute("**/health").catch(() => undefined);
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/model-providers") && url.includes("/configuration")) {
      return route.fulfill({
        json: {
          display_name: "阿里云百炼",
          plus_model: "qwen3.7-plus",
          max_model: "qwen3.7-max",
          flash_model: "qwen3.6-flash",
          credential_state: opts.connected ? "configured" : "missing",
          enabled: opts.connected,
          disconnected: !opts.connected,
          workspace_id: "ws-demo",
          base_url: "https://example.invalid",
          region: "cn-beijing",
          timeout_seconds: 300,
          max_retries: 3,
        },
      });
    }
    if (url.includes("/model-providers")) {
      return route.fulfill({ json: [provider] });
    }
    if (url.includes("/settings/cloud-budget")) {
      return route.fulfill({ json: budget });
    }
    if (url.includes("/settings/cloud")) {
      return route.fulfill({
        json: {
          enabled: opts.cloudEnabled,
          state: opts.cloudEnabled ? "enabled" : "disabled",
        },
      });
    }
    if (url.includes("/cloud-usage")) {
      return route.fulfill({
        json: {
          request_count: 0,
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          estimated_cost: 0,
          remaining_estimated_cost: 5,
          blocked_reasons: opts.cloudEnabled ? [] : ["云端总开关已关闭"],
        },
      });
    }
    if (url.includes("/cloud-pricing")) {
      return route.fulfill({
        json: { configured: true, valid: true, enabled: true, pricing_version: "v1" },
      });
    }
    if (url.includes("/system/diagnostics")) {
      return route.fulfill({ json: { fastapi: "ok", sqlite: "ok", python: "3.11" } });
    }
    if (url.includes("/settings/desktop")) {
      return route.fulfill({ json: { demo_mode: true, theme: "light" } });
    }
    if (url.includes("/model-routing")) {
      return route.fulfill({ json: [] });
    }
    if (url.match(/\/books\/?\d*$/) && !url.includes("chapters")) {
      if (url.endsWith("/books") || url.endsWith("/books/")) {
        return route.fulfill({
          json: [
            {
              id: 1,
              title: "演示小说",
              source_file_name: "demo.txt",
              source_file_hash: "abcd",
              created_at: "2026-01-01T00:00:00Z",
            },
          ],
        });
      }
      return route.fulfill({
        json: {
          id: 1,
          title: "演示小说",
          source_file_name: "demo.txt",
          source_file_hash: "abcd",
          created_at: "2026-01-01T00:00:00Z",
        },
      });
    }
    if (url.includes("/chapters") && !url.includes("paragraphs")) {
      return route.fulfill({
        json: [
          {
            id: 1,
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
              id: "B0001-C0001-P0001",
              chapter_id: 1,
              paragraph_index: 1,
              raw_text: "正文段落一。",
            },
          ],
        },
      });
    }
    if (url.includes("preflight") || url.includes("budget")) {
      return route.fulfill({
        json: {
          eligible: true,
          provider_state_version: "state-1",
          within_budget: true,
          exceeded_dimensions: [],
          paragraph_count: 10,
          transition_count: 9,
          detection_batch_count: 2,
          adjudication_batch_count_estimated: 1,
          expected_request_count: 3,
          worst_case_request_count: 6,
          estimated_total_tokens: 1000,
          worst_case_total_tokens: 2000,
          estimated_cost: 0.01,
          worst_case_cost: 0.02,
          currency: "CNY",
          remaining: { requests: 70, tokens: 90000, estimated_cost: 2.5 },
        },
      });
    }
    if (url.includes("/analysis-runs")) {
      return route.fulfill({ json: [] });
    }
    return route.fulfill({ json: {} });
  });
  await page.route("**/health", (route) =>
    route.fulfill({ json: { status: "ok", database: "ok" } }),
  );
}

async function shot(page: Page, name: string) {
  fs.mkdirSync(OUT, { recursive: true });
  const target = path.join(OUT, name);
  await page.screenshot({ path: target, fullPage: true });
  if (!fs.existsSync(target)) {
    throw new Error(`screenshot missing: ${target}`);
  }
}

test.describe("settings AI service UX screenshots", () => {
  test("capture required screenshots", async ({ page }) => {
    test.setTimeout(120000);
    await page.addInitScript(() => {
      if (!sessionStorage.getItem("storylens.screenshotInit")) {
        localStorage.setItem("storylens.developerMode", "0");
        sessionStorage.setItem("storylens.screenshotInit", "1");
      }
    });

    await mockApis(page, { connected: false, cloudEnabled: false });
    await page.goto("/settings");
    await expect(page.getByTestId("settings-page")).toBeVisible();
    await page.getByTestId("settings-tab-general").click();
    await expect(page.getByTestId("settings-panel-general")).toBeVisible();
    await shot(page, "01-settings-general.png");

    await page.getByTestId("settings-tab-ai").click();
    await expect(page.getByTestId("ai-service-status-card")).toBeVisible();
    await shot(page, "02-settings-ai-disconnected.png");

    await mockApis(page, { connected: true, cloudEnabled: true });
    await page.reload();
    await page.getByTestId("settings-tab-ai").click();
    await expect(page.getByTestId("ai-service-connection-status")).toContainText(
      /已连接|可以开始分析/,
    );
    await shot(page, "03-settings-ai-connected.png");

    await page.getByTestId("settings-tab-budget").click();
    await expect(page.getByTestId("settings-panel-budget")).toBeVisible();
    await shot(page, "04-settings-budget-privacy.png");

    await page.getByLabel("开发者模式").check();
    await expect(page.getByTestId("dev-nav-panel")).toBeVisible();
    await page.getByTestId("settings-tab-advanced").click();
    await expect(page.getByTestId("settings-panel-advanced")).toBeVisible();
    await shot(page, "05-settings-advanced-developer.png");

    await mockApis(page, { connected: true, cloudEnabled: true });
    await page.getByLabel("开发者模式").uncheck();
    await page.goto("/books/1");
    await expect(page.getByTestId("shell-start-analysis")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("shell-start-analysis").click({ force: true });
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-ai-connected")).toBeVisible();
    await shot(page, "06-start-analysis-connected.png");
    await page.getByRole("button", { name: "关闭" }).click();

    await mockApis(page, { connected: false, cloudEnabled: false });
    await page.reload();
    await expect(page.getByTestId("shell-start-analysis")).toBeVisible({ timeout: 15000 });
    await page.getByTestId("shell-start-analysis").click({ force: true });
    await expect(page.getByTestId("start-analysis-ai-disconnected")).toBeVisible();
    await expect(page.getByTestId("start-analysis-submit")).toBeDisabled();
    await shot(page, "07-start-analysis-disconnected.png");
  });
});
