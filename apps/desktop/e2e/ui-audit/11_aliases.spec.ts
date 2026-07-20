import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady, setTheme } from "./helpers/shot";

/** Fill inventory aliases / route extras not covered by primary specs. */
test.describe.configure({ mode: "serial" });
test.setTimeout(120_000);

test("inventory aliases and route extras", async ({ page }) => {
  await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  await installUiAuditMocks(page, {
    books: "multi",
    tasks: "multi",
    analysisRun: "succeeded",
    journey: "ready",
  });

  await gotoReady(page, "/");
  await shot(page, { id: "R-01", file: "r_home_redirect.png", route: "/", theme: "light" });
  await shot(page, { id: "R-02", file: "02_library_default.png", route: "/library", theme: "light" });

  await gotoReady(page, "/workspace");
  await shot(page, { id: "R-03", file: "r_workspace.png", route: "/workspace", theme: "light" });

  await gotoReady(page, "/tasks");
  await expect(page.getByTestId("run-101-progress")).toBeVisible();
  await expect(page.getByTestId("run-101-progress")).not.toContainText("undefined");
  await shot(page, { id: "R-05", file: "07_tasks_list.png", route: "/tasks", theme: "light" });

  await gotoReady(page, "/analysis-runs/55/results");
  await expect(page.getByTestId("results-shell")).toHaveAttribute("data-results-state", "completed");
  await expect(page.getByText("Unexpected Application Error")).toHaveCount(0);
  await shot(page, {
    id: "R-06",
    file: "05_analysis_results.png",
    route: "/analysis-runs/55/results",
    theme: "light",
  });

  await gotoReady(page, "/cases");
  await shot(page, { id: "R-07", file: "r_cases.png", route: "/cases", theme: "light" });

  await gotoReady(page, "/settings?tab=ai");
  await shot(page, {
    id: "R-09",
    file: "09_settings_ai_default.png",
    route: "/settings?tab=ai",
    theme: "light",
  });

  await gotoReady(page, "/library");
  await setTheme(page, "dark");
  await shot(page, { id: "dark-library", file: "02_library_dark.png", route: "/library", theme: "dark" });
  await setTheme(page, "light");

  // Native confirm cannot be screenshot mid-handler (deadlocks evaluate). Capture page note instead.
  await gotoReady(page, "/books/1?chapter=1");
  page.once("dialog", async (d) => {
    await d.dismiss();
  });
  await page.evaluate(() => window.confirm("审计确认对话框：是否继续？"));
  await shot(page, {
    id: "10-07",
    file: "10_confirm_dialog.png",
    route: "/books/1",
    theme: "light",
    notes: "browser native confirm is not capturable mid-dialog; page after dismiss",
  });
});
