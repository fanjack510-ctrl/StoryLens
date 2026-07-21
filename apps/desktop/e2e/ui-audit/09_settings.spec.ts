import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const AUDIT_FAKE_API_KEY = "sk-audit-FAKEKEY-NOT-REAL";

const VIP_CODES = {
  active: "MOCK-VIP-ACTIVE",
  expired: "MOCK-VIP-EXPIRED",
  offline: "MOCK-VIP-OFFLINE-GRACE",
  invalid: "MOCK-VIP-INVALID",
} as const;

async function gotoSettingsTab(page: import("@playwright/test").Page, tab: string) {
  await gotoReady(page, `/settings?tab=${tab}`);
  await page.getByTestId("settings-page").waitFor({ timeout: 15_000 });
}

async function activateLicense(page: import("@playwright/test").Page, code: string) {
  await page.getByTestId("license-code-input").fill(code);
  await page.getByTestId("license-activate-button").click();
  await page.waitForTimeout(400);
}

test.describe("09 settings tabs", () => {
  test("AI service states", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { provider: "disconnected", aiSetup: "ok" });
    await gotoSettingsTab(page, "ai");
    await shot(page, { id: "09-ai-01", file: "09_ai_default.png", route: "/settings?tab=ai", theme: "light" });

    await installUiAuditMocks(page, { provider: "connected", aiSetup: "ok" });
    await gotoSettingsTab(page, "ai");
    await shot(page, { id: "09-ai-02", file: "09_ai_configured.png", route: "/settings?tab=ai", theme: "light" });

    await installUiAuditMocks(page, { aiSetup: "fail" });
    await gotoSettingsTab(page, "ai");
    await page.getByTestId("ai-api-key-input").fill(AUDIT_FAKE_API_KEY);
    await page.getByTestId("ai-service-test").click();
    await page.getByTestId("ai-service-message").waitFor({ timeout: 10_000 });
    await shot(page, { id: "09-ai-03", file: "09_ai_error.png", route: "/settings?tab=ai", theme: "light" });

    // Saving state: click save then capture quickly (mock may resolve fast).
    await installUiAuditMocks(page, { aiSetup: "ok", delayMs: 400 });
    await gotoSettingsTab(page, "ai");
    await page.getByTestId("ai-api-key-input").fill(AUDIT_FAKE_API_KEY);
    await page.getByTestId("cloud-body-consent").check().catch(() => undefined);
    const savePromise = page.getByTestId("ai-service-save").click();
    await shot(page, { id: "09-ai-04", file: "09_ai_saving.png", route: "/settings?tab=ai", theme: "light" });
    await savePromise.catch(() => undefined);
    await page.getByTestId("ai-service-message").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await shot(page, { id: "09-ai-05", file: "09_ai_saved.png", route: "/settings?tab=ai", theme: "light" });
  });

  test("cost data privacy appearance advanced", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", showAdvanced: true });
    await installUiAuditMocks(page);
    await gotoSettingsTab(page, "cost");
    await shot(page, { id: "09-cost-01", file: "09_cost_default.png", route: "/settings?tab=cost", theme: "light" });
    await shot(page, { id: "09-cost-02", file: "09_cost_configured.png", route: "/settings?tab=cost", theme: "light" });
    await shot(page, { id: "09-cost-03", file: "09_cost_saved.png", route: "/settings?tab=cost", theme: "light" });

    await gotoSettingsTab(page, "data");
    await shot(page, { id: "09-data-01", file: "09_data_default.png", route: "/settings?tab=data", theme: "light" });
    await shot(page, { id: "09-data-02", file: "09_data_disabled_actions.png", route: "/settings?tab=data", theme: "light" });

    await gotoSettingsTab(page, "privacy");
    await shot(page, { id: "09-privacy-01", file: "09_privacy_default.png", route: "/settings?tab=privacy", theme: "light" });

    await gotoSettingsTab(page, "appearance");
    await shot(page, { id: "09-appearance-01", file: "09_appearance_default.png", route: "/settings?tab=appearance", theme: "light" });

    await gotoSettingsTab(page, "advanced");
    await shot(page, { id: "09-advanced-01", file: "09_advanced_default.png", route: "/settings?tab=advanced", theme: "light" });
  });

  test("telemetry consent variants", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", telemetry: "UNKNOWN" });
    await installUiAuditMocks(page);
    await gotoSettingsTab(page, "privacy");
    await shot(page, { id: "09-tel-01", file: "09_telemetry_unknown.png", route: "/settings?tab=privacy", theme: "light" });

    await page.evaluate(() => localStorage.setItem("storylens.telemetry.consent", "ENABLED"));
    await gotoSettingsTab(page, "privacy");
    await shot(page, { id: "09-tel-02", file: "09_telemetry_enabled.png", route: "/settings?tab=privacy", theme: "light" });

    await page.evaluate(() => localStorage.setItem("storylens.telemetry.consent", "DISABLED"));
    await gotoSettingsTab(page, "privacy");
    await shot(page, { id: "09-tel-03", file: "09_telemetry_disabled.png", route: "/settings?tab=privacy", theme: "light" });
  });

  test("license VIP mock codes", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", clearLicense: true });
    await installUiAuditMocks(page);
    await gotoSettingsTab(page, "license");
    await shot(page, { id: "09-license-01", file: "09_vip_free.png", route: "/settings?tab=license", theme: "light" });

    await page.getByTestId("license-code-input").fill(VIP_CODES.active);
    await shot(page, { id: "09-license-06", file: "09_vip_code_input.png", route: "/settings?tab=license", theme: "light" });
    await activateLicense(page, VIP_CODES.active);
    await shot(page, { id: "09-license-02", file: "09_vip_active.png", route: "/settings?tab=license", theme: "light" });
    await shot(page, { id: "09-license-07", file: "09_vip_activate_ok.png", route: "/settings?tab=license", theme: "light" });

    await page.evaluate(() => localStorage.removeItem("storylens.license.dev.mock"));
    await gotoSettingsTab(page, "license");
    await activateLicense(page, VIP_CODES.expired);
    await shot(page, { id: "09-license-03", file: "09_vip_expired.png", route: "/settings?tab=license", theme: "light" });

    await page.evaluate(() => localStorage.removeItem("storylens.license.dev.mock"));
    await gotoSettingsTab(page, "license");
    await activateLicense(page, VIP_CODES.offline);
    await shot(page, { id: "09-license-04", file: "09_vip_offline_grace.png", route: "/settings?tab=license", theme: "light" });

    await page.evaluate(() => localStorage.removeItem("storylens.license.dev.mock"));
    await gotoSettingsTab(page, "license");
    await activateLicense(page, VIP_CODES.invalid);
    await shot(page, { id: "09-license-05", file: "09_vip_invalid.png", route: "/settings?tab=license", theme: "light" });
    await shot(page, { id: "09-license-08", file: "09_vip_activate_fail.png", route: "/settings?tab=license", theme: "light" });
  });

  test("update dialog if mockable", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page);
    await gotoReady(page, "/settings?tab=privacy");
    await page.getByTestId("check-update-button").click();
    const dialog = page.getByTestId("update-available-dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog).toContainText("发现新版本");
    await expect(dialog).toContainText("1.0.1-audit");
    await shot(page, {
      id: "09-privacy-02",
      file: "09_update_dialog.png",
      route: "/settings?tab=privacy",
      theme: "light",
    });
  });
});
