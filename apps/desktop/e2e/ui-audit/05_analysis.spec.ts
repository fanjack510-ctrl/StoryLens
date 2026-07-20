import { test, expect } from "@playwright/test";
import { installUiAuditMocks } from "./helpers/mockApi";
import { shot, prepareAuditSession, gotoReady } from "./helpers/shot";

test.describe.configure({ mode: "serial" });
test.setTimeout(180_000);

const BOOK = "/books/1?chapter=1";

async function openStartAnalysis(page: import("@playwright/test").Page) {
  await page.getByTestId("shell-start-analysis").click();
  await page.getByTestId("start-analysis-dialog").waitFor();
  // Developer mode defaults to local; switch to cloud so Provider states are meaningful.
  const modeSelect = page.getByLabel(/执行模式|执行方式/);
  if (await modeSelect.count()) {
    await modeSelect.selectOption("cloud");
  }
}

test.describe("05 analysis", () => {
  test.beforeEach(async ({ page }) => {
    await prepareAuditSession(page, { onboarding: "completed", developerMode: true });
  });

  test("unanalyzed", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "none", tasks: "empty" });
    await gotoReady(page, BOOK);
    await shot(page, { id: "05-01", file: "05_unanalyzed.png", route: BOOK, theme: "light" });
  });

  test("start dialog connected", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "connected",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-provider-select")).toBeVisible();
    await expect(page.getByTestId("start-analysis-dialog")).toContainText("创建分析任务");
    await expect(page.getByTestId("start-analysis-mode-section")).toBeVisible();
    await shot(page, { id: "05-02", file: "05_start_dialog.png", route: BOOK, theme: "light" });
    const tech = page.getByTestId("start-analysis-tech-details");
    if (await tech.count()) {
      await tech.locator("summary").click();
    }
    await expect(page.getByTestId("start-analysis-dialog")).toContainText("aliyun_qwen_plus");
    await shot(page, { id: "05-03", file: "05_provider_single.png", route: BOOK, theme: "light" });
    await page.getByRole("checkbox").check().catch(() => undefined);
    await shot(page, { id: "05-15", file: "05_confirm_budget.png", route: BOOK, theme: "light" });
    await shot(page, {
      id: "05-d1",
      file: "05_start_dialog_dark.png",
      route: BOOK,
      theme: "dark",
    });
  });

  test("start dialog provider none", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "none",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toContainText(
      /尚未配置 API Key|当前没有可用/,
    );
    await shot(page, { id: "05-05", file: "05_provider_none.png", route: BOOK, theme: "light" });
  });

  test("start dialog cloud off", async ({ page }) => {
    await installUiAuditMocks(page, {
      cloudEnabled: false,
      provider: "connected",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toContainText(
      /云端分析尚未开启|云端连接未开启/,
    );
    await shot(page, { id: "05-06", file: "05_cloud_off.png", route: BOOK, theme: "light" });
  });

  test("start dialog key missing", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "disconnected",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toContainText("尚未配置 API Key");
    await shot(page, { id: "05-07", file: "05_key_missing.png", route: BOOK, theme: "light" });
    await shot(page, { id: "05-10", file: "05_goto_ai_settings.png", route: BOOK, theme: "light" });
  });

  test("start dialog provider disabled", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "disabled",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toContainText(
      /AI 服务已停用|Provider 已停用/,
    );
    await shot(page, { id: "05-08", file: "05_provider_disabled.png", route: BOOK, theme: "light" });
  });

  test("start dialog invalid credential", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "invalid_cred",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-dialog")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toBeVisible();
    await expect(page.getByTestId("start-analysis-no-provider")).toContainText(
      /保存的凭据已失效|凭据无效/,
    );
    await shot(page, { id: "05-09", file: "05_credential_invalid.png", route: BOOK, theme: "light" });
  });

  test("multi provider developer mode", async ({ page }) => {
    await installUiAuditMocks(page, {
      multiProviders: true,
      provider: "connected",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("start-analysis-provider-select")).toBeVisible();
    await shot(page, { id: "05-04", file: "05_provider_multi.png", route: BOOK, theme: "light" });
  });

  test("analysis modes in dialog", async ({ page }) => {
    await installUiAuditMocks(page, {
      provider: "connected",
      tasks: "empty",
      analysisRun: "none",
    });
    await gotoReady(page, BOOK);
    await openStartAnalysis(page);
    await expect(page.getByTestId("analysis-mode-fast")).toBeVisible();
    await page.getByTestId("analysis-mode-fast").click();
    await expect(page.getByTestId("start-analysis-mode-hint")).toContainText("速度优先");
    await shot(page, { id: "05-11", file: "05_mode_fast.png", route: BOOK, theme: "light" });
    await page.getByTestId("analysis-mode-balanced").click();
    await shot(page, { id: "05-12", file: "05_mode_balanced.png", route: BOOK, theme: "light" });
    await page.getByTestId("analysis-mode-quality").click();
    await shot(page, { id: "05-13", file: "05_mode_quality.png", route: BOOK, theme: "light" });
    if (await page.getByTestId("analysis-mode-custom").count()) {
      await page.getByTestId("analysis-mode-custom").click();
    }
    await shot(page, {
      id: "05-14",
      file: "05_mode_custom.png",
      route: BOOK,
      theme: "light",
      notes: "CUSTOM in start dialog developer mode",
    });
  });

  test("progress running and failed retry done", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "running" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=progress`);
    await page.getByTestId("chapter-analysis-progress").waitFor({ timeout: 10_000 });
    await expect(page.getByTestId("chapter-analysis-stages")).toBeVisible();
    await expect(page.getByTestId("chapter-analysis-progress")).not.toContainText("Scene Analysis");
    await shot(page, { id: "05-16", file: "05_analyzing.png", route: BOOK, theme: "light" });
    await shot(page, { id: "05-17", file: "05_progress.png", route: BOOK, theme: "light" });
    await shot(page, {
      id: "05-d2",
      file: "05_analysis_progress_dark.png",
      route: BOOK,
      theme: "dark",
    });

    await installUiAuditMocks(page, { analysisRun: "failed" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=progress`);
    await page.getByTestId("chapter-analysis-failure").waitFor({ timeout: 10_000 }).catch(() => undefined);
    await expect(page.getByTestId("chapter-analysis-progress")).toContainText(/分析未完成|分析已暂停/);
    await shot(page, { id: "05-18", file: "05_failed.png", route: BOOK, theme: "light" });
    const retry = page.getByTestId("chapter-analysis-reanalyze");
    if (await retry.count()) {
      await shot(page, { id: "05-19", file: "05_retry.png", route: BOOK, theme: "light" });
    }

    await installUiAuditMocks(page, { analysisRun: "budget_pause" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=progress`);
    await expect(page.getByTestId("chapter-analysis-progress")).toContainText("分析已暂停");
    await shot(page, { id: "05-19b", file: "05_paused.png", route: BOOK, theme: "light" });

    await installUiAuditMocks(page, { analysisRun: "succeeded" });
    await gotoReady(page, `${BOOK}&analysisRun=55&view=result`);
    await shot(page, { id: "05-20", file: "05_done.png", route: BOOK, theme: "light" });
    await gotoReady(page, "/analysis-runs/55/results");
    await expect(page.getByTestId("results-shell")).toBeVisible();
    await expect(page.getByTestId("results-shell")).toHaveAttribute("data-results-state", "completed");
    await expect(page.getByText("Unexpected Application Error")).toHaveCount(0);
    await shot(page, {
      id: "05-25",
      file: "05_scene_analysis_result.png",
      route: "/analysis-runs/55/results",
      theme: "light",
    });
  });

  test("boundary review from more menu", async ({ page }) => {
    await installUiAuditMocks(page, { analysisRun: "succeeded" });
    await page.route("**/books/1/chapters/1/boundary-review**", async (route) => {
      if (route.request().method() !== "GET") {
        return route.fulfill({ json: {} });
      }
      return route.fulfill({
        json: {
          id: 7,
          book_id: 1,
          chapter_id: 1,
          analysis_run_id: 55,
          status: "in_review",
          provider: "aliyun_qwen_plus",
          model: "qwen3.7-plus",
          prompt_version: "v3.5",
          accepted_count: 1,
          rejected_count: 0,
          manually_added_count: 0,
          paragraphs: [
            { id: "B0001-C0001-P0001", chapter_id: 1, paragraph_index: 1, raw_text: "虚构段落一" },
            { id: "B0001-C0001-P0002", chapter_id: 1, paragraph_index: 2, raw_text: "虚构段落二" },
          ],
          decisions: [
            {
              id: 1,
              transition_id: "T0001",
              left_paragraph_id: "B0001-C0001-P0001",
              right_paragraph_id: "B0001-C0001-P0002",
              model_candidate: true,
              model_confidence: 0.8,
              user_decision: "pending",
              review_priority: "high",
              model_reason_code: "location_change",
            },
          ],
        },
      });
    });
    await page.route("**/boundary-reviews/**/scene-preview**", async (route) => {
      return route.fulfill({ json: { review_id: 7, coverage_rate: 1, scenes: [{ ordinal: 1 }] } });
    });
    await gotoReady(page, BOOK);
    await page.getByTestId("book-more-menu-trigger").click();
    await page.getByTestId("book-more-boundary-review").click();
    await page.getByTestId("shell-boundary-review").waitFor({ timeout: 15_000 });
    await expect(page.getByTestId("shell-boundary-review")).toContainText("审阅中");
    await expect(page.getByTestId("shell-boundary-review")).toContainText("待处理");
    await expect(page.getByTestId("shell-boundary-review")).not.toContainText("in_review");
    await expect(page.getByTestId("book-shell-body")).toHaveCount(0);
    await shot(page, {
      id: "05-21",
      file: "05_boundary_list.png",
      route: BOOK,
      theme: "light",
      notes: "Boundary focus mode",
    });
    const confirmBtn = page.getByTestId("confirm-all-boundaries");
    if (await confirmBtn.count()) {
      await shot(page, { id: "05-22", file: "05_boundary_confirm.png", route: BOOK, theme: "light" });
    }
    const editCard = page.getByTestId("decision-card-T0001");
    if (await editCard.count()) {
      await editCard.click().catch(() => undefined);
      await shot(page, { id: "05-23", file: "05_boundary_edit.png", route: BOOK, theme: "light" });
    }
    await shot(page, { id: "05-24", file: "05_boundary_save.png", route: BOOK, theme: "light" });
    await shot(page, {
      id: "05-d3",
      file: "05_boundary_review_dark.png",
      route: BOOK,
      theme: "dark",
    });
  });
});
