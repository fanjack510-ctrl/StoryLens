import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady, setTheme } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

test.describe("10 global", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.removeItem("storylens.uiAudit.forceBootstrap");
    });
  });

  test("bootstrap starting", async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem("storylens.uiAudit.forceBootstrap", "starting");
    });
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-starting").waitFor();
    await shot(page, {
      id: "00-01",
      file: "00_global_bootstrap_starting.png",
      route: "/",
      theme: "light",
    });
  });

  test("bootstrap failed", async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem("storylens.uiAudit.forceBootstrap", "failed");
    });
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-error").waitFor();
    await shot(page, {
      id: "00-02",
      file: "00_global_bootstrap_failed.png",
      route: "/",
      theme: "light",
    });
  });

  test("shell light dark and devmode", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: false });
    await installUiAuditMocks(page, { books: "one" });
    await gotoReady(page, "/library");
    await shot(page, { id: "00-03", file: "00_shell_light.png", route: "/library", theme: "light" });
    await setTheme(page, "dark");
    await shot(page, { id: "00-04", file: "00_shell_dark.png", route: "/library", theme: "dark" });
    await setTheme(page, "light");
    await shot(page, { id: "00-05", file: "00_devmode_off.png", route: "/library", theme: "light" });

    await page.evaluate(() => localStorage.setItem("storylens.developerMode", "1"));
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByTestId("desktop-bootstrap-starting").waitFor({ state: "hidden", timeout: 15000 }).catch(() => undefined);
    await expect(page.getByTestId("dev-nav-panel")).toBeVisible({ timeout: 10000 }).catch(async () => {
      const toggle = page.getByTestId("dev-nav-toggle");
      if (await toggle.count()) await toggle.check();
    });
    await shot(page, { id: "00-06", file: "00_devmode_on.png", route: "/library", theme: "light" });
  });

  test("api 500 on books", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page);
    await page.route("**/api/v1/books**", async (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({ status: 500, json: { detail: "审计 Mock：书库 API 500" } });
      }
      return route.continue();
    });
    await gotoReady(page, "/library");
    await expect(page.getByTestId("error-state")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("error-state")).toContainText(/无法读取数据|500|审计 Mock/);
    await shot(page, { id: "10-04", file: "10_api_500.png", route: "/library", theme: "light" });
  });

  test("loading timeout not found", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { books: "one", chapterMode: "loading", paragraphsDelayMs: 8_000 });
    await gotoReady(page, "/books/1?chapter=1");
    await shot(page, {
      id: "10-01",
      file: "10_loading.png",
      route: "/books/1?chapter=1",
      theme: "light",
      notes: "章节段落加载中（短延迟 Mock）",
    });
    await shot(page, {
      id: "10-05",
      file: "10_timeout.png",
      route: "/books/1?chapter=1",
      theme: "light",
      notes: "加载态近似网络超时等待（审计）",
    });

    await installUiAuditMocks(page, { healthOk: false });
    await gotoReady(page, "/library");
    await expect(page.getByTestId("error-state")).toBeVisible({ timeout: 15_000 });
    await shot(page, {
      id: "10-02",
      file: "10_api_failed.png",
      route: "/library",
      theme: "light",
      notes: "Health/books abort simulated as API failure ErrorState",
    });

    await page.goto("/no-such-page-audit-404", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("not-found-page")).toBeVisible();
    await expect(page.getByTestId("not-found-page")).toContainText("页面未找到");
    await expect(page.getByTestId("not-found-library")).toBeVisible();
    await shot(page, {
      id: "10-03",
      file: "10_not_found.png",
      route: "/no-such-page-audit-404",
      theme: "light",
    });
  });

  test("form validation and disabled controls", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "pending" });
    await installUiAuditMocks(page);
    await gotoReady(page, "/library");
    await page.getByRole("button", { name: "下一步" }).click({ timeout: 8_000 });
    await page.getByTestId("onboarding-save-next").click({ timeout: 8_000 });
    await page.getByTestId("onboarding-ai-message").waitFor({ timeout: 8_000 });
    await shot(page, { id: "10-08", file: "10_form_validation.png", route: "/library", theme: "light" });

    await page.evaluate(() => {
      localStorage.setItem("storylens.onboarding.v1", "completed");
    });
    await installUiAuditMocks(page);
    await gotoReady(page, "/settings?tab=data");
    await shot(page, { id: "10-09", file: "10_disabled_button.png", route: "/settings?tab=data", theme: "light" });
  });

  test("dropdown popover tooltip empty long titles", async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { books: "multi" });
    await gotoReady(page, "/library");
    await page.getByTestId("library-sort").click();
    await shot(page, { id: "10-11", file: "10_dropdown.png", route: "/library", theme: "light" });

    await installUiAuditMocks(page, { books: "long_titles", chapterMode: "long_title" });
    await gotoReady(page, "/books/1?chapter=1");
    await page.getByTestId("reading-settings-trigger").click();
    await page.getByTestId("reading-settings-panel").waitFor();
    await shot(page, { id: "10-12", file: "10_popover.png", route: "/books/1?chapter=1", theme: "light" });

    const titled = page.locator("[title]:visible").first();
    if (await titled.count()) {
      await titled.hover({ timeout: 5_000 }).catch(() => undefined);
      await shot(page, { id: "10-10", file: "10_tooltip.png", route: "/books/1?chapter=1", theme: "light" });
    } else {
      await shot(page, {
        id: "10-10",
        file: "10_tooltip.png",
        route: "/books/1?chapter=1",
        theme: "light",
        notes: "no visible title tooltip target",
      });
    }

    await prepareAuditSession(page, { onboarding: "completed" });
    await installUiAuditMocks(page, { tasks: "empty", analysisRun: "none" });
    await gotoReady(page, "/tasks");
    await shot(page, { id: "10-13", file: "10_empty_table.png", route: "/tasks", theme: "light" });

    await installUiAuditMocks(page, { books: "long_titles" });
    await gotoReady(page, "/library");
    await shot(page, { id: "10-14", file: "10_long_book_title.png", route: "/library", theme: "light" });

    await installUiAuditMocks(page, { chapterMode: "long_title" });
    await gotoReady(page, "/books/1?chapter=1");
    await shot(page, { id: "10-15", file: "10_long_chapter_title.png", route: "/books/1?chapter=1", theme: "light" });
  });
});
