import { test, expect } from "@playwright/test";

test("navigation and offline-safe shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("StoryLens").first()).toBeVisible();
  await expect(page.getByTestId("library-page")).toBeVisible();
  await page.getByTestId("dev-nav-toggle").click();
  await page.getByRole("link", { name: "模型与API" }).click();
  await expect(page.getByRole("heading", { name: "模型与 API" })).toBeVisible();
  // Old routes remain directly reachable
  await page.goto("/cases");
  await expect(page.getByText("演示数据")).toBeVisible();
});
