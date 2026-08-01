import { expect, test, type Page } from "@playwright/test";
import { buildVisualizationFixture } from "./fixtures/readerJourneyE2eFixtures";

/**
 * CHG-20260731-025: right-rail「查看阅读旅程」must navigate like top「阅读旅程」.
 * Runs against Vite/build preview with mocked API (no real Provider).
 */

const visualization = buildVisualizationFixture();

async function mockSucceededJourneyApis(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();

    if (url.includes("/health")) {
      return route.fulfill({
        json: { status: "ok", database: "ok", default_provider: "fake" },
      });
    }
    if (url.includes("/books/1/chapters") && !url.includes("paragraphs")) {
      return route.fulfill({
        json: [
          {
            id: 2,
            book_id: 1,
            chapter_index: 1,
            section_type: "chapter",
            title: "第一章",
            display_title: "第一章",
          },
        ],
      });
    }
    if (url.match(/\/books\/1(?:\?|$)/) || url.endsWith("/books/1")) {
      return route.fulfill({
        json: {
          id: 1,
          title: "CHG-025 Fixture",
          source_file_name: "chg025.txt",
          source_file_hash: "abcd",
          created_at: "2026-01-01T00:00:00Z",
        },
      });
    }
    if (url.includes("/analysis-runs/77") && !url.includes("results") && method === "GET") {
      return route.fulfill({
        json: {
          id: 77,
          subject_id: "2",
          subject_type: "chapter",
          provider: "fake",
          model: "fake",
          status: "succeeded",
          progress_current: 3,
          progress_total: 3,
          execution_mode: "cloud",
          cloud_consent: true,
          sends_content_to_cloud: true,
          retryable: false,
          created_at: "2026-01-01T00:00:00Z",
          completed_at: "2026-01-01T01:00:00Z",
          chapter_complete: true,
          effective_status: "complete",
          journey_status: "succeeded",
          journey_result_available: true,
          completed_scene_count: 3,
          total_scene_count: 3,
        },
      });
    }
    if (url.includes("/analysis-runs/77/results")) {
      return route.fulfill({
        json: {
          run: { id: 77, status: "succeeded", provider: "fake", model: "fake" },
          chapter: { id: 2, book_id: 1, title: "第一章", display_title: "第一章" },
          boundary_revision: { id: 3, revision_number: 1 },
          summary: { total_scene_count: 3 },
          scenes: [],
        },
      });
    }
    if (url.includes("/scene-boundaries/overview") || url.includes("/scene-boundaries-overview")) {
      return route.fulfill({
        json: {
          chapter_id: 2,
          chapter_text_hash: "h",
          confirmed_revision: {
            revision_id: 3,
            revision_number: 1,
            status: "confirmed",
            source: "user",
            scenes: [{ ordinal: 1 }, { ordinal: 2 }, { ordinal: 3 }],
          },
          draft_revision: null,
          model_revision: null,
          awaiting_confirmation: false,
        },
      });
    }
    if (
      url.includes("/reader-journey-runs/12") ||
      (url.includes("/reader-journey") && url.includes("analysis"))
    ) {
      return route.fulfill({
        json: {
          status: "succeeded",
          journey_run_id: 12,
          analysis_run_id: 77,
          book_id: 1,
          chapter_id: 2,
          visualization,
          journey_result: visualization,
        },
      });
    }
    if (url.includes("/reader-journey") || url.includes("journey")) {
      return route.fulfill({
        json: {
          status: "succeeded",
          journey_run_id: 12,
          analysis_run_id: 77,
          visualization,
          completed_scene_count: 3,
          total_scene_count: 3,
        },
      });
    }
    if (url.includes("/settings/") || url.includes("/cloud")) {
      return route.fulfill({
        json: {
          remaining_requests: 50,
          remaining_tokens: 900000,
          remaining_estimated_cost: 20,
        },
      });
    }
    if (method === "POST" && (url.includes("/resume") || url.includes("/recover"))) {
      return route.fulfill({ status: 500, json: { detail: "unexpected side effect" } });
    }
    return route.fulfill({ status: 404, json: { detail: `unmocked ${method} ${url}` } });
  });
}

test.describe("CHG-025 right-rail journey CTA", () => {
  test("right-rail and top nav open the same journey result without resume", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      localStorage.setItem("storylens.onboarding.v1", "completed");
      localStorage.setItem("storylens.developerMode", "1");
      localStorage.setItem("storylens.telemetry.consent", "denied");
    });
    await mockSucceededJourneyApis(page);

    const resumePosts: string[] = [];
    const recoverPosts: string[] = [];
    page.on("request", (req) => {
      if (req.method() !== "POST") return;
      const url = req.url();
      if (/\/resume(?:\/|$|\?)/.test(url)) resumePosts.push(url);
      if (/\/recover(?:\/|$|\?)/.test(url)) recoverPosts.push(url);
    });

    await page.goto(
      "/books/1?chapter=2&analysisRun=77&view=progress&journeyRun=12",
    );
    await expect(page.getByTestId("chapter-analysis-open-journey")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByTestId("chapter-analysis-open-journey")).toHaveText(
      "查看阅读旅程",
    );

    await page.getByTestId("chapter-analysis-open-journey").click();
    await expect(page).toHaveURL(/view=result/);
    await expect(page).toHaveURL(/tab=reader-journey/);
    await expect(page).toHaveURL(/analysisRun=77/);
    await expect(page).toHaveURL(/journeyRun=12/);
    await expect(page.getByTestId("journey-workspace").or(page.getByTestId("journey-export-title")).or(page.getByTestId("workspace-tab-journey"))).toBeVisible();

    const afterRight = page.url();

    await page.getByTestId("shell-view-analysis-progress-secondary").click();
    await expect(page).toHaveURL(/view=progress/);

    await page.getByTestId("workspace-tab-journey").click();
    await expect(page).toHaveURL(/view=result/);
    await expect(page).toHaveURL(/tab=reader-journey/);
    await expect(page).toHaveURL(/analysisRun=77/);
    await expect(page).toHaveURL(/journeyRun=12/);

    const afterTop = page.url();
    const normalize = (u: string) => {
      const url = new URL(u);
      const keys = ["chapter", "analysisRun", "journeyRun", "view", "tab"];
      return keys.map((k) => `${k}=${url.searchParams.get(k)}`).join("&");
    };
    expect(normalize(afterTop)).toBe(normalize(afterRight));
    expect(resumePosts).toEqual([]);
    expect(recoverPosts).toEqual([]);
  });
});
