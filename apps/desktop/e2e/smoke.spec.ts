import { test, expect } from "@playwright/test";

test("navigation and offline-safe shell", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("storylens.onboarding.v1", "completed");
    localStorage.setItem("storylens.developerMode", "1");
    localStorage.setItem("storylens.telemetry.consent", "denied");
  });
  await page.goto("/");
  await expect(page.getByText("StoryLens").first()).toBeVisible();
  await expect(page.getByTestId("library-page")).toBeVisible();
  await expect(page.getByTestId("first-launch-wizard")).toHaveCount(0);
  await expect(page.getByTestId("appearance-theme-trigger")).toBeVisible();

  // Dismiss optional first-run AI setup card if present (non-blocking chrome).
  const later = page.getByRole("button", { name: "稍后" });
  if (await later.isVisible().catch(() => false)) {
    await later.click();
  }

  await expect(page.getByTestId("dev-nav-panel")).toBeVisible();
  await page.getByRole("link", { name: "模型与 API" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "模型与 API" })).toBeVisible();

  await page.goto("/cases");
  await expect(page.getByText("演示数据")).toBeVisible();
});
