import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

test.describe("07 tasks", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("empty list", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "empty", analysisRun: "none" });
    await gotoReady(page, "/tasks");
    await shot(page, { id: "07-01", file: "07_tasks_empty.png", route: "/tasks", theme: "light" });
  });

  test("one running", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "one_running" });
    await gotoReady(page, "/tasks");
    await shot(page, { id: "07-02", file: "07_tasks_one_running.png", route: "/tasks", theme: "light" });
  });

  test("multi statuses", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "multi" });
    await gotoReady(page, "/tasks");
    await expect(page.getByTestId("run-101-progress")).toBeVisible();
    await expect(page.getByTestId("run-101-progress")).not.toContainText("undefined");
    await expect(page.getByTestId("run-102-progress")).not.toContainText("undefined");
    await shot(page, { id: "07-03", file: "07_tasks_multi.png", route: "/tasks", theme: "light" });
    await shot(page, { id: "07-04", file: "07_status_queued.png", route: "/tasks", theme: "light" });
    await shot(page, { id: "07-05", file: "07_status_running.png", route: "/tasks", theme: "light" });
    await shot(page, { id: "07-06", file: "07_status_done.png", route: "/tasks", theme: "light" });
    await shot(page, { id: "07-07", file: "07_status_failed.png", route: "/tasks", theme: "light" });
    await shot(page, {
      id: "07-08",
      file: "07_status_cancelled.png",
      route: "/tasks",
      theme: "light",
      notes: "Cancelled row included in multi mock when API returns cancelled",
    });
    const retry = page.getByTestId("unified-recover-open-104");
    if (await retry.count()) {
      await shot(page, { id: "07-09", file: "07_retry_button.png", route: "/tasks", theme: "light" });
    }
  });

  test("detail modal and error detail", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "multi" });
    await gotoReady(page, "/tasks");
    await page.getByTestId("view-detail-104").click();
    await expect(page.getByRole("heading", { name: "任务详情" })).toBeVisible();
    await expect(page.getByTestId("detail-evidence-error")).toBeVisible();
    await expect(page.getByTestId("detail-evidence-error")).toContainText("证据段落越界");
    await shot(page, { id: "07-10", file: "07_task_detail.png", route: "/tasks", theme: "light" });
    await page.getByTestId("invocation-safe-details").locator("summary").click();
    await expect(page.getByText("审计模拟 Invocation 失败")).toBeVisible();
    await shot(page, { id: "07-11", file: "07_task_error_detail.png", route: "/tasks", theme: "light" });
  });

  test("long list", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "long" });
    await gotoReady(page, "/tasks");
    await shot(page, { id: "07-14", file: "07_tasks_long.png", route: "/tasks", theme: "light", fullPage: true });
  });
});
