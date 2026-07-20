import { test, expect, type Page } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

/** Password-field-only audit placeholder; never log or echo this value. */
const AUDIT_FAKE_API_KEY = "sk-audit-FAKEKEY-NOT-REAL";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

async function openWizardStep2(page: Page) {
  await page.getByTestId("first-launch-wizard").waitFor({ state: "visible" });
  await page.getByTestId("onboarding-step-welcome").waitFor();
  await page.getByRole("button", { name: "下一步" }).click();
  await page.getByTestId("onboarding-step-ai").waitFor();
}

test.describe("01 onboarding", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "pending", developerMode: false });
  });

  test("welcome", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await page.getByTestId("onboarding-step-welcome").waitFor();
    await shot(page, {
      id: "01-01",
      file: "01_onboarding_welcome.png",
      route: "/library",
      theme: "light",
    });
  });

  test("AI blank", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await shot(page, {
      id: "01-02",
      file: "01_onboarding_ai_blank.png",
      route: "/library",
      theme: "light",
    });
  });

  test("API key masked", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await shot(page, {
      id: "01-03",
      file: "01_onboarding_ai_key_masked.png",
      route: "/library",
      theme: "light",
    });
  });

  test("consent off", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await shot(page, {
      id: "01-07",
      file: "01_onboarding_consent_off.png",
      route: "/library",
      theme: "light",
    });
  });

  test("consent on", async ({ page }) => {
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await page.locator(".consent input[type=checkbox]").first().check();
    await shot(page, {
      id: "01-08",
      file: "01_onboarding_consent_on.png",
      route: "/library",
      theme: "light",
    });
  });

  test("test pending", async ({ page }) => {
    await installUiAuditMocks(page, { aiSetup: "pending" });
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await page.locator(".consent input[type=checkbox]").first().check();
    await page.getByTestId("onboarding-test").click();
    await expect(page.getByTestId("onboarding-test")).toContainText("测试中");
    await shot(page, {
      id: "01-04",
      file: "01_onboarding_test_pending.png",
      route: "/library",
      theme: "light",
    });
  });

  test("test ok", async ({ page }) => {
    await installUiAuditMocks(page, { aiSetup: "ok" });
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await page.locator(".consent input[type=checkbox]").first().check();
    await page.getByTestId("onboarding-test").click();
    await page.getByTestId("onboarding-ai-message").waitFor();
    await shot(page, {
      id: "01-05",
      file: "01_onboarding_test_ok.png",
      route: "/library",
      theme: "light",
    });
  });

  test("test fail", async ({ page }) => {
    await installUiAuditMocks(page, { aiSetup: "fail" });
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await page.locator(".consent input[type=checkbox]").first().check();
    await page.getByTestId("onboarding-test").click();
    await page.getByTestId("onboarding-ai-message").waitFor();
    await shot(page, {
      id: "01-06",
      file: "01_onboarding_test_fail.png",
      route: "/library",
      theme: "light",
    });
  });

  test("finish step3", async ({ page }) => {
    await installUiAuditMocks(page, { aiSetup: "ok" });
    await gotoReady(page, "/library");
    await openWizardStep2(page);
    await page.getByTestId("onboarding-api-key").fill(AUDIT_FAKE_API_KEY);
    await page.locator(".consent input[type=checkbox]").first().check();
    await page.getByTestId("onboarding-save-next").click();
    await page.getByTestId("onboarding-step-start").waitFor({ timeout: 30_000 });
    await shot(page, {
      id: "01-09",
      file: "01_onboarding_done.png",
      route: "/library",
      theme: "light",
    });
  });

  test("skipped library", async ({ page }) => {
    await installUiAuditMocks(page, { books: "empty" });
    await gotoReady(page, "/library");
    await page.getByRole("button", { name: "跳过向导" }).click();
    await page.getByTestId("library-page").waitFor();
    await expect(page.getByTestId("first-launch-wizard")).toHaveCount(0);
    await shot(page, {
      id: "01-10",
      file: "01_onboarding_skipped_library.png",
      route: "/library",
      theme: "light",
      notes: "No separate skip confirmation dialog in product",
    });
  });
});

test.describe("01 onboarding settings follow-ups", () => {
  test("reenter configured settings", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { provider: "connected", aiSetup: "ok" });
    await gotoReady(page, "/settings?tab=ai");
    await page.getByTestId("settings-panel-ai-service").waitFor();
    await shot(page, {
      id: "01-11",
      file: "01_onboarding_reenter_configured.png",
      route: "/settings?tab=ai",
      theme: "light",
    });
  });

  test("needs repair", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { aiSetup: "needs_repair" });
    await gotoReady(page, "/settings?tab=ai");
    await page.getByTestId("settings-panel-ai-service").waitFor();
    await shot(page, {
      id: "01-12",
      file: "01_onboarding_needs_repair.png",
      route: "/settings?tab=ai",
      theme: "light",
    });
  });

  test("qwen banner empty library", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { books: "empty", provider: "disconnected" });
    await gotoReady(page, "/library");
    const banner = page.getByTestId("qwen-first-launch-banner");
    if (await banner.count()) {
      await banner.waitFor();
    }
    await shot(page, {
      id: "01-13",
      file: "01_qwen_banner.png",
      route: "/library",
      theme: "light",
      notes: (await banner.count()) ? undefined : "Banner hidden when provider reads as configured",
    });
  });
});
