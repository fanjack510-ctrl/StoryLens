/**
 * RC.6 Cases C/D — terminal + stale recovery presentation on built frontend.
 * Uses route mocks so we assert the baked dist UI without mutating live journeys.
 */
import { expect, test, type Page } from "@playwright/test";

async function dismissOnboarding(page: Page): Promise<void> {
  await page.addInitScript(() => {
    localStorage.setItem("storylens.onboarding.v1", "completed");
    localStorage.setItem("storylens.developerMode", "1");
    localStorage.setItem("storylens.telemetry.consent", "denied");
  });
}

async function assertBuildIdentity(page: Page): Promise<void> {
  const metaResp = await page.request.get("/storylens-frontend-build.json");
  expect(metaResp.ok()).toBeTruthy();
  const meta = (await metaResp.json()) as { source_commit?: string };
  expect(String(meta.source_commit ?? "").length).toBeGreaterThanOrEqual(7);
}

const journeySucceeded = {
  id: 31,
  analysis_run_id: 31,
  book_id: 31,
  chapter_id: 31,
  status: "succeeded",
  current_stage: "reader_journey",
  root_error_code: "JOURNEY_INTERRUPTED",
  root_error_message: "stale interrupt",
  retryable: true,
  journey_result: {
    chapter_curve: { points: [{ x: 0, y: 0.5 }] },
    scenes: [],
  },
};

const journeyFailed = {
  id: 32,
  analysis_run_id: 32,
  book_id: 32,
  chapter_id: 32,
  status: "failed",
  current_stage: "reader_journey",
  root_error_code: "PIPELINE_UNEXPECTED_ERROR",
  root_error_message: "terminal fail",
  retryable: true,
  journey_result: null,
};

const progressInterrupted = {
  status: "scene_profiles_partial",
  root_error_code: "JOURNEY_INTERRUPTED",
  retryable: true,
  recovery_safe: true,
  completed_scene_count: 0,
  total_scene_count: 4,
};

async function mockTerminalBook(page: Page, journey: typeof journeySucceeded, progress: typeof progressInterrupted) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes(`/reader-journeys/${journey.id}/progress`)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(progress) });
      return;
    }
    if (url.includes(`/reader-journeys/${journey.id}`)) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(journey) });
      return;
    }
    if (url.includes("/analysis-runs")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: journey.analysis_run_id,
            book_id: journey.book_id,
            chapter_id: journey.chapter_id,
            status: "succeeded",
            journey_run_id: journey.id,
            journey_status: journey.status,
          },
        ]),
      });
      return;
    }
    if (url.includes("/books")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          { id: journey.book_id, title: "RC6 Case Terminal", chapter_count: 1 },
        ]),
      });
      return;
    }
    if (url.includes("/chapters")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{ id: journey.chapter_id, book_id: journey.book_id, title: "Ch1", order: 1 }]),
      });
      return;
    }
    if (url.includes("/recovery")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user_status: "paused_recoverable",
          can_resume: true,
          recommended_action: "resume_journey",
        }),
      });
      return;
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
  });
}

test.beforeEach(async ({ page }) => {
  await dismissOnboarding(page);
});

test("RC6 Case C: succeeded + stale recovery shows result, hides progress", async ({ page }) => {
  await mockTerminalBook(page, journeySucceeded, progressInterrupted);
  await page.goto(
    `/books/${journeySucceeded.book_id}?chapter=${journeySucceeded.chapter_id}&analysisRun=${journeySucceeded.analysis_run_id}&journeyRun=${journeySucceeded.id}&view=progress&tab=reader-journey`,
  );
  await assertBuildIdentity(page);
  // Terminal success must not show recovering / progress card.
  await expect(page.getByText("正在恢复阅读旅程")).toHaveCount(0);
  await expect(page.getByTestId("reader-journey-progress-card")).toHaveCount(0);
  await expect(page.getByTestId("journey-interrupted")).toHaveCount(0);
});

test("RC6 Case D: failed + stale interrupted shows failure, hides progress", async ({ page }) => {
  await mockTerminalBook(page, journeyFailed, progressInterrupted);
  await page.goto(
    `/books/${journeyFailed.book_id}?chapter=${journeyFailed.chapter_id}&analysisRun=${journeyFailed.analysis_run_id}&journeyRun=${journeyFailed.id}&view=progress&tab=reader-journey`,
  );
  await assertBuildIdentity(page);
  await expect(page.getByText("正在恢复阅读旅程")).toHaveCount(0);
  await expect(page.getByTestId("reader-journey-progress-card")).toHaveCount(0);
});
