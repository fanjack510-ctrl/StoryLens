import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const DEFAULT_FIXTURES = resolve(
  REPO_ROOT,
  "release/evidence/hotfix/1.1.2/CHG-20260731-023/acceptance/MANUAL_FIXTURES.json",
);
type FixtureEntry = {
  url: string;
  journey_run_id: number;
  book_id: number;
};

type ManualFixtures = {
  resume_failure: FixtureEntry;
  resume_success: FixtureEntry;
  api_url: string;
};

function loadFixtures(): ManualFixtures {
  const path = process.env.CHG023_FIXTURES_JSON ?? DEFAULT_FIXTURES;
  return JSON.parse(readFileSync(path, "utf8")) as ManualFixtures;
}

/** Reseed MG DB — orchestration script normally runs this between order swaps. */
export function reseedChg023FinalFixtures(): void {
  const py =
    process.env.STORYLENS_PYTHON ??
    (process.platform === "win32" ? "python" : "python3");
  const seedScript = resolve(REPO_ROOT, "apps/api/scripts_seed_chg023_final_mg.py");
  execFileSync(py, [seedScript], {
    cwd: REPO_ROOT,
    stdio: "inherit",
    env: { ...process.env },
  });
}

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
  const commit = String(meta.source_commit ?? "");
  expect(commit.length).toBeGreaterThanOrEqual(7);
  const short = commit.slice(0, 7);
  const fingerprint = page.getByTestId("runtime-dev-fingerprint");
  await expect(fingerprint).toBeVisible({ timeout: 15_000 });
  await expect(fingerprint).toContainText(short);
}

type NetworkTracker = {
  resumePosts: string[];
  recoverPosts: string[];
};

function trackJourneyResumeNetwork(page: Page, journeyRunId: number): NetworkTracker {
  const tracker: NetworkTracker = { resumePosts: [], recoverPosts: [] };
  const resumeRe = new RegExp(`/reader-journey-runs/${journeyRunId}/resume`);
  page.on("request", (req) => {
    if (req.method() !== "POST") return;
    const url = req.url();
    if (resumeRe.test(url)) tracker.resumePosts.push(url);
    if (/\/recover(?:\/|$|\?)/.test(url)) tracker.recoverPosts.push(url);
  });
  return tracker;
}

async function runCaseA(page: Page, fixtures: ManualFixtures): Promise<void> {
  const fail = fixtures.resume_failure;
  const api = fixtures.api_url || process.env.CHG023_API_URL || "http://127.0.0.1:18067";
  const beforeAr = await page.request.get(`${api}/api/v1/analysis-runs`);
  const arCount0 = ((await beforeAr.json()) as unknown[]).length;
  const beforeJourney = await page.request.get(`${api}/api/v1/reader-journeys/${fail.journey_run_id}`);
  expect(beforeJourney.ok()).toBeTruthy();

  const tracker = trackJourneyResumeNetwork(page, fail.journey_run_id);

  await page.goto(fail.url);
  await expect(page.getByTestId("journey-interrupted")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("journey-interrupted-continue")).toBeVisible();
  await expect(page.getByTestId("runtime-dev-fingerprint")).toBeVisible();

  await page.getByTestId("journey-interrupted-continue").click();

  await expect(page.getByTestId("journey-failed")).toBeVisible({ timeout: 90_000 });
  await expect(page.getByText("正在恢复阅读旅程")).toHaveCount(0);
  await expect(page.getByTestId("journey-interrupted-continue")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "继续分析" })).toHaveCount(0);
  await expect(page.getByTestId("reader-journey-progress-card")).toHaveCount(0);
  await expect(page.getByTestId("chapter-analysis-continue-journey")).toHaveCount(0);

  await expect.poll(() => tracker.resumePosts.length, { timeout: 15_000 }).toBe(1);
  expect(tracker.recoverPosts).toHaveLength(0);

  const afterAr = await page.request.get(`${api}/api/v1/analysis-runs`);
  expect(((await afterAr.json()) as unknown[]).length).toBe(arCount0);

  // Same journey id must remain the only bound run (no new journey created).
  const dbJourney = await page.request.get(`${api}/api/v1/reader-journeys/${fail.journey_run_id}`);
  expect(dbJourney.ok()).toBeTruthy();
  expect(((await dbJourney.json()) as { status: string }).status).toBe("failed");
  const ghost = await page.request.get(`${api}/api/v1/reader-journeys/${fail.journey_run_id + 1000}`);
  expect(ghost.status()).toBe(404);

  await assertBuildIdentity(page);
}

async function runCaseB(page: Page, fixtures: ManualFixtures): Promise<void> {
  const ok = fixtures.resume_success;
  const api = fixtures.api_url || process.env.CHG023_API_URL || "http://127.0.0.1:18067";
  const beforeAr = await page.request.get(`${api}/api/v1/analysis-runs`);
  const arCount0 = ((await beforeAr.json()) as unknown[]).length;
  const tracker = trackJourneyResumeNetwork(page, ok.journey_run_id);

  await page.goto(ok.url);
  await expect(page.getByTestId("journey-interrupted")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("journey-interrupted-continue").click();

  // Succeeded journey renders WorkspaceJourneyPane (not EmbeddedAnalysisResultShell).
  await expect(page.getByTestId("workspace-journey-pane")).toBeVisible({ timeout: 180_000 });
  await expect(page.getByTestId("workspace-journey-pane")).toHaveAttribute("data-state", "ready");
  await expect(page.getByText("正在恢复阅读旅程")).toHaveCount(0);
  await expect(page.getByTestId("reader-journey-progress-card")).toHaveCount(0);
  await expect(page.getByTestId("journey-curve-svg")).toBeVisible();
  await expect(page.getByTestId("journey-interrupted")).toHaveCount(0);
  await expect(page.getByTestId("journey-failed")).toHaveCount(0);
  // Conflicting resume CTAs must stay absent (progress rail may dismiss after success).
  await expect(page.getByTestId("chapter-analysis-continue-journey")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "继续分析" })).toHaveCount(0);

  await expect.poll(() => tracker.resumePosts.length, { timeout: 15_000 }).toBe(1);
  expect(tracker.recoverPosts).toHaveLength(0);
  expect(((await (await page.request.get(`${api}/api/v1/analysis-runs`)).json()) as unknown[]).length).toBe(
    arCount0,
  );

  const dbJourney = await page.request.get(`${api}/api/v1/reader-journeys/${ok.journey_run_id}`);
  expect(dbJourney.ok()).toBeTruthy();
  const body = (await dbJourney.json()) as { status: string; journey_result?: unknown };
  expect(body.status).toBe("succeeded");
  expect(body.journey_result ?? null).not.toBeNull();

  await assertBuildIdentity(page);
}

const fixtures = loadFixtures();
const testOrder = process.env.CHG023_TEST_ORDER ?? "fail-first";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ page }) => {
  await dismissOnboarding(page);
});

if (testOrder === "success-first") {
  test("CHG023 case B: resume success final state @success", async ({ page }) => {
    await runCaseB(page, fixtures);
  });
  test("CHG023 case A: resume failure final state @fail", async ({ page }) => {
    await runCaseA(page, fixtures);
  });
} else {
  test("CHG023 case A: resume failure final state @fail", async ({ page }) => {
    await runCaseA(page, fixtures);
  });
  test("CHG023 case B: resume success final state @success", async ({ page }) => {
    await runCaseB(page, fixtures);
  });
}

test("CHG023 case B only: success after API restart @success-only", async ({ page }) => {
  test.skip(process.env.CHG023_RUN_SUCCESS_ONLY !== "1", "Set CHG023_RUN_SUCCESS_ONLY=1");
  await runCaseB(page, fixtures);
});
