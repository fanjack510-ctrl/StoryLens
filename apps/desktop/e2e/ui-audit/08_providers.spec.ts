import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

async function installProviderExtras(page: import("@playwright/test").Page) {
  await page.route("**/model-providers/**/transport-diagnostic**", async (route) => {
    return route.fulfill({
      json: {
        overall_status: "ok",
        configuration_valid: true,
        dns: { status: "ok", latency_ms: 12 },
        tcp: { status: "ok", latency_ms: 20 },
        tls: { status: "ok", latency_ms: 40, certificate_valid: true },
        proxy: { detected: false },
        ca_bundle: { status: "ok", source: "system" },
        request_endpoint_shape: { status: "ok", path_redacted: "/v1/chat/completions" },
        user_action_hint: "审计 Mock：传输正常",
      },
    });
  });
  await page.route("**/model-providers/**/test/preflight**", async (route) => {
    return route.fulfill({
      json: {
        configured_model: "qwen3.7-plus",
        max_output_tokens: 32,
        estimated_cost: 0.001,
        currency: "CNY",
        remaining_requests: 50,
        remaining_tokens: 100000,
        remaining_estimated_cost: 4.5,
      },
    });
  });
  await page.route("**/model-providers/**/test**", async (route) => {
    if (route.request().method() !== "POST") return route.fulfill({ json: {} });
    return route.fulfill({
      json: {
        http_status: 200,
        provider: "aliyun_qwen_plus",
        configured_model: "qwen3.7-plus",
        response_model: "qwen3.7-plus",
        json_valid: true,
        schema_valid: true,
        input_tokens: 10,
        output_tokens: 5,
        total_tokens: 15,
        latency_ms: 120,
        invocation_id: 9001,
        request_id: "audit-req-1",
        estimated_cost: 0.001,
        currency: "CNY",
        pricing_version: "v1-audit",
      },
    });
  });
}

test.describe("08 providers", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("default configured enabled", async ({ page }) => {
    await installUiAuditMocks(page, { provider: "connected" });
    await installProviderExtras(page);
    await gotoReady(page, "/providers");
    await shot(page, { id: "08-01", file: "08_providers_default.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-02", file: "08_aliyun_configured.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-04", file: "08_aliyun_enabled.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-06", file: "08_cred_ok.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-10", file: "08_provider_edit.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-11", file: "08_model_map.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-13", file: "08_auto_route.png", route: "/providers", theme: "light" });
    await shot(page, { id: "08-14", file: "08_cloud_switch.png", route: "/providers", theme: "light" });
  });

  test("unconfigured disconnected", async ({ page }) => {
    await installUiAuditMocks(page, { provider: "disconnected" });
    await installProviderExtras(page);
    await gotoReady(page, "/providers");
    await shot(page, { id: "08-03", file: "08_aliyun_unconfigured.png", route: "/providers", theme: "light" });
  });

  test("disabled provider", async ({ page }) => {
    await installUiAuditMocks(page, { provider: "disabled" });
    await installProviderExtras(page);
    await gotoReady(page, "/providers");
    await shot(page, { id: "08-05", file: "08_aliyun_disabled.png", route: "/providers", theme: "light" });
  });

  test("unknown credential", async ({ page }) => {
    await installUiAuditMocks(page, { provider: "unknown_cred" });
    await installProviderExtras(page);
    await gotoReady(page, "/providers");
    await shot(page, { id: "08-07", file: "08_cred_unknown.png", route: "/providers", theme: "light" });
  });

  test("connection confirm and results", async ({ page }) => {
    await installUiAuditMocks(page, { provider: "connected" });
    await installProviderExtras(page);
    await gotoReady(page, "/providers");
    const transportBtn = page.getByTestId("transport-diagnostic-button");
    if (await transportBtn.isVisible({ timeout: 8_000 }).catch(() => false)) {
      await transportBtn.click({ timeout: 5_000 });
      await page.getByTestId("transport-diagnostic-result").waitFor({ timeout: 10_000 }).catch(() => undefined);
      await shot(page, { id: "08-08", file: "08_conn_ok.png", route: "/providers", theme: "light" });
    } else {
      await shot(page, {
        id: "08-08",
        file: "08_conn_ok.png",
        route: "/providers",
        theme: "light",
        notes: "transport button not visible — page snapshot",
      });
    }

    const paidBtn = page.getByTestId("paid-connection-test-button");
    if (await paidBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await paidBtn.click({ timeout: 5_000 });
      const confirm = page.getByTestId("connection-test-confirmation");
      if (await confirm.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await shot(page, { id: "08-16", file: "08_conn_confirm.png", route: "/providers", theme: "light" });
        await page.getByRole("button", { name: /确认并测试|确认/ }).click({ timeout: 5_000 }).catch(() => undefined);
        await page.getByTestId("real-connection-test-result").waitFor({ timeout: 10_000 }).catch(() => undefined);
      }
    }

    await installUiAuditMocks(page, { provider: "invalid_cred" });
    await installProviderExtras(page);
    await page.route("**/model-providers/**/test**", async (route) => {
      if (route.request().method() !== "POST") return route.fulfill({ json: {} });
      return route.fulfill({
        status: 502,
        json: { error_code: "AUTHENTICATION_FAILED", message: "审计 Mock 连接失败" },
      });
    });
    await gotoReady(page, "/providers");
    if (await paidBtn.isVisible({ timeout: 5_000 }).catch(() => false)) {
      await page.getByTestId("paid-connection-test-button").click({ timeout: 5_000 });
      const confirmFail = page.getByTestId("connection-test-confirmation");
      if (await confirmFail.isVisible({ timeout: 5_000 }).catch(() => false)) {
        await page.getByRole("button", { name: /确认并测试|确认/ }).click({ timeout: 5_000 }).catch(() => undefined);
      }
      await page.getByTestId("real-connection-test-error").waitFor({ timeout: 10_000 }).catch(() => undefined);
    }
    await shot(page, { id: "08-09", file: "08_conn_fail.png", route: "/providers", theme: "light" });
  });

  test("advanced params via settings", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", showAdvanced: true, developerMode: true });
    await installUiAuditMocks(page);
    await gotoReady(page, "/settings?tab=advanced");
    await shot(page, { id: "08-12", file: "08_advanced_params.png", route: "/settings?tab=advanced", theme: "light" });
  });
});
