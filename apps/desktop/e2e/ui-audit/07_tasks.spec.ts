import { test, expect } from "@playwright/test";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { installUiAuditMocks } from "./helpers/mockApi";
import {
  shot,
  prepareAuditSession,
  gotoReady,
  applyProductTheme,
  assertAnalysisDarkSurfaces,
  SCREENSHOT_DIR,
} from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

function fileSha256(file: string): string {
  const buf = fs.readFileSync(path.join(SCREENSHOT_DIR, file));
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function assertScreenshotsDiffer(a: string, b: string, label: string) {
  const pathA = path.join(SCREENSHOT_DIR, a);
  const pathB = path.join(SCREENSHOT_DIR, b);
  if (!fs.existsSync(pathA) || !fs.existsSync(pathB)) {
    throw new Error(`${label}: missing screenshot ${!fs.existsSync(pathA) ? a : b}`);
  }
  expect(fileSha256(a), `${label}: ${a} vs ${b} must differ`).not.toBe(fileSha256(b));
}

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
    await expect(page.getByRole("columnheader", { name: "任务" })).toBeVisible();
    await expect(page.getByRole("columnheader", { name: "状态" })).toBeVisible();
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
    const more = page.getByTestId("run-more-104-trigger");
    if (await more.count()) {
      await more.click();
      await shot(page, { id: "07-09", file: "07_retry_button.png", route: "/tasks", theme: "light" });
    }

    await applyProductTheme(page, "dark");
    await assertAnalysisDarkSurfaces(page);
    await shot(page, {
      id: "07-d1",
      file: "07_tasks_list_dark.png",
      route: "/tasks",
      theme: "dark",
    });
    assertScreenshotsDiffer("07_tasks_multi.png", "07_tasks_list_dark.png", "tasks light vs dark");
    await applyProductTheme(page, "light");
  });

  test("detail modal and error detail", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "multi" });
    await gotoReady(page, "/tasks");
    await page.getByTestId("view-detail-104").click();
    await expect(page.getByRole("heading", { name: "任务详情" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "基本信息" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "执行过程" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "用量" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "错误信息" })).toBeVisible();
    await expect(page.getByTestId("detail-evidence-error")).toBeVisible();
    await expect(page.getByTestId("detail-evidence-error")).toContainText("证据段落越界");
    await expect(page.getByTestId("task-raw-error")).not.toHaveAttribute("open", "");
    await shot(page, { id: "07-10", file: "07_task_detail.png", route: "/tasks", theme: "light" });
    await page.getByTestId("invocation-safe-details").locator("summary").click();
    await expect(page.getByText("审计模拟 Invocation 失败")).toBeVisible();
    await shot(page, { id: "07-11", file: "07_task_error_detail.png", route: "/tasks", theme: "light" });

    await applyProductTheme(page, "dark");
    await assertAnalysisDarkSurfaces(page);
    await shot(page, {
      id: "07-d2",
      file: "07_task_detail_dark.png",
      route: "/tasks",
      theme: "dark",
    });
    assertScreenshotsDiffer("07_task_detail.png", "07_task_detail_dark.png", "task detail light vs dark");
  });

  test("long list", async ({ page }) => {
    await installUiAuditMocks(page, { tasks: "long" });
    await gotoReady(page, "/tasks");
    await shot(page, { id: "07-14", file: "07_tasks_long.png", route: "/tasks", theme: "light", fullPage: true });
  });
});
