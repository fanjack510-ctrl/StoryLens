import { test, expect } from "@playwright/test";

async function mockProviderApis(page: import("@playwright/test").Page, diagnostic: Record<string, unknown>) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes("/model-providers/aliyun_qwen_plus/test/preflight") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider: "aliyun_qwen_plus",
          configured_model: "qwen3.7-plus",
          max_output_tokens: 32,
          max_real_requests: 1,
          estimated_cost: 0.001,
          currency: "CNY",
          pricing_version: "fake-v1",
          remaining_requests: 20,
          remaining_tokens: 90000,
          remaining_estimated_cost: 2.5,
          within_budget: true,
          blockers: [],
          sends_user_content: false,
        }),
      });
    }
    if (url.includes("/model-providers/aliyun_qwen_plus/test") && method === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 300));
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "healthy",
          http_status: 200,
          provider: "aliyun_qwen_plus",
          configured_model: "qwen3.7-plus",
          response_model: "qwen3.7-plus-fake-response",
          json_valid: true,
          schema_valid: true,
          input_tokens: 37,
          output_tokens: 6,
          total_tokens: 43,
          latency_ms: 120,
          invocation_id: 92,
          estimated_cost: 0.001,
          currency: "CNY",
          pricing_version: "fake-v1",
          request_id: "rid#fake",
          retryable: false,
        }),
      });
    }
    if (url.includes("/model-providers/aliyun_qwen_plus/transport-diagnostic") && method === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(diagnostic),
      });
    }
    if (url.includes("/model-providers") && method === "GET" && !url.includes("configuration")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            capability_schema_version: "1c-a-2",
            name: "aliyun_qwen_plus",
            default_model: "qwen3.7-plus",
            enabled: true,
            healthy: true,
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
          },
        ]),
      });
    }
    if (url.includes("/settings/cloud")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: true, state: "enabled" }),
      });
    }
    if (url.includes("/settings/cloud-budget") || url.includes("/cloud-budget")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          cloud_request_budget_enabled: true,
          cloud_daily_estimated_cost_limit: 5,
          currency: "CNY",
        }),
      });
    }
    if (url.includes("cloud-usage") || url.includes("usage")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          request_count: 0,
          total_tokens: 0,
          estimated_cost: 0,
          remaining_estimated_cost: 5,
          blocked_reasons: [],
        }),
      });
    }
    if (url.includes("pricing")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: true, valid: true, configured: true }),
      });
    }
    if (url.includes("routing")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    if (url.includes("configuration")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          provider_name: "aliyun_qwen_plus",
          enabled: true,
          credential_state: "configured",
          base_url: "",
        }),
      });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

const baseDiag = {
  provider: "aliyun_qwen_plus",
  configuration_valid: true,
  dns: { status: "ok", latency_ms: 1 },
  tcp: { status: "ok", latency_ms: 2 },
  tls: { status: "ok", latency_ms: 3, certificate_valid: true },
  proxy: { detected: false, source: null },
  ca_bundle: { status: "ok", source: "certifi" },
  request_endpoint_shape: { status: "ok", path_redacted: "/…/compatible-mode/v1/chat/completions" },
  overall_status: "ok",
  error_code: null,
  user_action_hint: null,
  generates_tokens: false,
  creates_invocation: false,
  calls_chat_completions: false,
  note: "传输诊断不会调用模型，不消耗Token。",
};

test.describe("Provider transport diagnostic e2e (fake)", () => {
  test("诊断成功不产生真实云端调用", async ({ page }) => {
    await mockProviderApis(page, baseDiag);
    await page.goto("/providers");
    await page.getByTestId("transport-diagnostic-button").click();
    await expect(page.getByTestId("transport-diagnostic-result")).toContainText("ok");
    await expect(page.getByText(/不消耗Token/)).toBeVisible();
  });

  test("DNS失败结果展示", async ({ page }) => {
    await mockProviderApis(page, {
      ...baseDiag,
      overall_status: "failed",
      dns: { status: "failed", latency_ms: 5 },
      tcp: { status: "skipped" },
      tls: { status: "skipped" },
      error_code: "PROVIDER_DNS_ERROR",
      user_action_hint: "检查DNS",
    });
    await page.goto("/providers");
    await page.getByTestId("transport-diagnostic-button").click();
    await expect(page.getByTestId("transport-diagnostic-result")).toContainText("DNS");
    await expect(page.getByTestId("transport-diagnostic-result")).toContainText("解析失败");
  });

  test("TLS失败与ConnectTimeout展示", async ({ page }) => {
    await mockProviderApis(page, {
      ...baseDiag,
      overall_status: "failed",
      dns: { status: "ok", latency_ms: 1 },
      tcp: { status: "ok", latency_ms: 2 },
      tls: { status: "failed", latency_ms: 4, certificate_valid: false },
      error_code: "PROVIDER_TLS_ERROR",
      user_action_hint: "检查证书",
    });
    await page.goto("/providers");
    await page.getByTestId("transport-diagnostic-button").click();
    await expect(page.getByTestId("transport-diagnostic-result")).toContainText("TLS");
  });

  test("真实连接测试确认、运行与结果均可见且使用Fake", async ({ page }) => {
    await mockProviderApis(page, baseDiag);
    await page.goto("/providers");
    await page.getByTestId("transport-diagnostic-button").click();
    await expect(page.getByText("传输诊断结果")).toBeVisible();

    await page.getByTestId("paid-connection-test-button").click();
    const confirmation = page.getByTestId("connection-test-confirmation");
    await expect(confirmation).toBeVisible();
    await expect(confirmation).toContainText("原创最小JSON请求");
    await expect(confirmation).toContainText("不发送用户小说正文");
    await confirmation.getByRole("button", { name: "确认并测试" }).click();

    await expect(page.getByText("正在发送原创最小测试请求……")).toBeVisible();
    await expect(page.getByTestId("paid-connection-test-button")).toBeDisabled();
    const result = page.getByTestId("real-connection-test-result");
    await expect(result).toBeVisible();
    await expect(result).toContainText("真实连接测试结果：成功");
    await expect(result).toContainText("qwen3.7-plus-fake-response");
    await expect(result).toContainText("43");
    await expect(result).toContainText("#92");
    await expect(page.getByText("传输诊断结果")).toBeVisible();
  });
});
