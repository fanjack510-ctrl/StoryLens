/**
 * WB-2.2 / CHG-20260803-041 — Playwright chapter functions UI.
 * Entry: TEST-ONLY harness (not final WholeBookFreeProductPage wiring).
 * TEST DATA ONLY via fixtures / route mocks. No real provider / formal DB writes.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

const BOOK_ID = 1;
const RUN_ID = 42;
const HARNESS = "/dev/whole-book-free-chapter-functions-harness";

const STRUCTURE_SMOKE = {
  result_status: "completed",
  coverage_scope: "full_selected_range",
  structure: {
    contract_version: "v2",
    evidence_contract_version: "v2",
    coverage_scope: "full_selected_range",
    analysis_confidence: 0.86,
    stages: [
      {
        local_stage_ref: "S1",
        order_index: 0,
        title: "开局承压",
        summary: {
          value: "试炼开始",
          status: "observed",
          citation_ids: ["CIT-TEST0001-0001"],
          confidence: 0.8,
        },
        start_boundary: { citation_ids: ["CIT-TEST0001-0001"] },
        end_boundary: { citation_ids: ["CIT-TEST0001-0001"] },
        chapter_range: [1, 2],
        confidence: 0.8,
      },
    ],
    turning_points: [],
  },
  citation_evidence_bindings: [{ citation_id: "CIT-TEST0001-0001", evidence_id: 501 }],
};

function completedRun() {
  return {
    run_id: RUN_ID,
    book_id: BOOK_ID,
    snapshot_id: 11,
    mode: "whole_book_native",
    status: "completed",
    current_stage_code: "finalize",
    idempotency_key: "e2e-cf",
    engine_id: "fixture-engine",
    engine_version: "v1",
    contract_version: "whole_book_contract_v1",
    prompt_version: null,
    result_origin: "fixture",
    input_usage: {
      full_text_snapshot_used: true,
      chapter_analysis_asset_count: 0,
      reader_journey_asset_count: 0,
      confirmed_whole_book_asset_count: 0,
    },
    consent_id: null,
    cost_policy_id: null,
    created_at: "2026-08-03T00:00:00Z",
    started_at: "2026-08-03T00:01:00Z",
    paused_at: null,
    completed_at: "2026-08-03T01:00:00Z",
    failed_at: null,
    cancelled_at: null,
    failure_code: null,
    failure_message_safe: null,
  };
}

function prepareBody() {
  return {
    book_id: BOOK_ID,
    book_title: "E2E CF Book",
    chapter_count: 12,
    character_count: 120000,
    mode: "whole_book_native",
    mode_label: "原生全书分析",
    product_enabled: true,
    real_provider_enabled: false,
    run_creation_enabled: false,
    fixture_preview_enabled: false,
    latest_run: completedRun(),
    recoverable_run: null,
    snapshot_rebuild_required: false,
    estimate: null,
    recommended_limits: {
      max_provider_calls: 200,
      max_input_tokens: 500000,
      max_output_tokens: 100000,
      max_cost_budget_cny: "10.00",
    },
    blocking_reasons: [],
    warnings: [],
  };
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function installFreePageMocks(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("storylens.onboarding.v1", "completed");
    localStorage.setItem("storylens.developerMode", "1");
    localStorage.setItem("storylens.telemetry.consent", "denied");
  });

  await page.route("**/api/v1/**", async (route) => {
    const url = route.request().url();
    if (url.includes("/whole-book/product-capabilities")) {
      return json(route, { capabilities: [] });
    }
    if (
      url.includes(`/books/${BOOK_ID}/whole-book/prepare`) ||
      url.includes(`/books/${BOOK_ID}/whole-book/free/prepare`)
    ) {
      return json(route, prepareBody());
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/structure`)) {
      return json(route, STRUCTURE_SMOKE);
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/overview`)) {
      return json(route, {
        overview: {
          result_version: "v1",
          contract_version: "whole_book_contract_v1",
          run_id: RUN_ID,
          book_id: BOOK_ID,
          snapshot_id: 11,
          mode: "whole_book_native",
          result_origin: "fixture",
          status: "completed",
          important_entity_ids: [],
          key_event_asset_ids: [],
          warnings: [],
          created_at: "2026-08-03T01:00:00Z",
          claims: [
            {
              claim_key: "genre_and_narrative_features",
              availability: "available",
              summary: "玄幻",
              confidence: 0.9,
              evidence_ids: [501],
              supporting_asset_ids: [],
              conflict_ids: [],
            },
          ],
        },
      });
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/entities`)) {
      return json(route, { entities: [] });
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/assets`)) {
      return json(route, { assets: [], total: 0, offset: 0, limit: 50 });
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/evidences`)) {
      return json(route, { evidences: [] });
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/stages`)) {
      return json(route, { stages: [] });
    }
    if (url.includes(`/books/${BOOK_ID}`) && !url.includes("whole-book")) {
      return json(route, { id: BOOK_ID, title: "E2E CF Book" });
    }
    if (url.includes(`/books/${BOOK_ID}/chapters`)) {
      return json(route, [
        {
          id: 1,
          book_id: BOOK_ID,
          chapter_index: 1,
          title: "第1章",
          display_title: "第1章",
          section_type: "chapter",
        },
      ]);
    }
    if (url.includes("/entitlements")) {
      return json(route, { tier: "free", features: [] });
    }
    if (url.includes("/analysis-runs")) {
      return json(route, []);
    }
    if (url.includes("/health")) {
      return json(route, { status: "ok" });
    }
    return json(route, { error_code: "MOCK_UNHANDLED", url }, 404);
  });
}

async function measureHarnessLayout(page: Page) {
  return page.evaluate(() => {
    const root = document.querySelector('[data-testid="chapter-functions-harness-page"]');
    const list = document.querySelector('[data-testid="whole-book-free-chapter-functions-list"]');
    return {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      rootOk: Boolean(root),
      listWidth: list ? (list as HTMLElement).offsetWidth : 0,
      hasPurchase: /购买|升级\s*Pro|立即开通|License|VIP/.test(document.body.innerText),
      rowCount: document.querySelectorAll(
        '[data-testid^="whole-book-free-chapter-functions-row-"]',
      ).length,
    };
  });
}

test.describe("WB-2.2 chapter functions harness", () => {
  test("harness entry + available + multi-label + no purchase @1920", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`${HARNESS}?fixture=B`);
    await expect(page.getByTestId("chapter-functions-harness-page")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "available",
    );
    await expect(page.getByTestId("cf-primary-label")).toHaveAttribute("data-wire", "climax");
    await expect(page.getByTestId("cf-primary-label")).toContainText("高潮");
    await expect(page.getByTestId("cf-secondary-labels")).toContainText("回溯");
    await expect(page.getByTestId("cf-secondary-labels")).toContainText("支线章");
    const m = await measureHarnessLayout(page);
    expect(m.hasPurchase).toBeFalsy();
    expect(m.scrollWidth).toBeLessThanOrEqual(m.clientWidth + 1);
  });

  test("partial + primary=null + filter UI", async ({ page }) => {
    await page.goto(`${HARNESS}?fixture=E`);
    await expect(page.getByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "partial",
    );
    await expect(page.getByTestId("whole-book-free-chapter-functions-partial-banner")).toBeVisible();

    await page.goto(`${HARNESS}?fixture=C`);
    await expect(page.getByTestId("cf-primary-null")).toContainText("未识别出足够可靠的主要功能");

    await page.goto(`${HARNESS}?fixture=A`);
    await page.getByTestId("whole-book-free-chapter-functions-filter-function").selectOption("setup");
    await expect(page.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
      "setup",
    );
    await page.getByTestId("whole-book-free-chapter-functions-clear-filters").click();
    await expect(page.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
      "",
    );
  });

  test("detail + evidence jump + return state + refresh", async ({ page }) => {
    await page.goto(`${HARNESS}?fixture=Q`);
    await page.getByTestId("whole-book-free-chapter-functions-detail-btn-1").click();
    await expect(page.getByTestId("whole-book-free-chapter-functions-detail")).toHaveAttribute(
      "data-chapter-id",
      "1",
    );
    await page.getByTestId("whole-book-free-chapter-functions-filter-function").selectOption("climax");
    await page.getByTestId("whole-book-free-chapter-functions-detail-evidence").click();
    await expect(page).toHaveURL(/returnModule=chapter_functions/);
    await expect(page).toHaveURL(/startOffset=1/);
    await expect(page).toHaveURL(/endOffset=5/);

    await page.goto(
      `${HARNESS}?fixture=Q&restoreChapter=1&restoreFunction=climax&returnModule=chapter_functions`,
    );
    await expect(page.getByTestId("whole-book-free-chapter-functions-detail")).toHaveAttribute(
      "data-chapter-id",
      "1",
    );
    await expect(page.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
      "climax",
    );

    await page.reload();
    await expect(page.getByTestId("whole-book-free-chapter-functions")).toHaveAttribute(
      "data-state",
      "available",
    );
    await expect(page.getByTestId("whole-book-free-chapter-functions-filter-function")).toHaveValue(
      "climax",
    );
  });

  test("1299 mock pagination does not render all rows", async ({ page }) => {
    await page.goto(`${HARNESS}?fixture=L`);
    await expect(page.getByTestId("chapter-functions-harness-item-count")).toHaveText("50");
    await page.getByTestId("whole-book-free-chapter-functions-load-more").click();
    await expect(page.getByTestId("chapter-functions-harness-item-count")).toHaveText("100");
    const rows = await page.locator('[data-testid^="whole-book-free-chapter-functions-row-"]').count();
    expect(rows).toBe(100);
    expect(rows).toBeLessThan(1299);
  });

  test("1366×768 drawer / no horizontal scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await page.goto(`${HARNESS}?fixture=A&drawer=1`);
    await page.getByTestId("whole-book-free-chapter-functions-detail-btn-1").click();
    await expect(page.getByTestId("whole-book-free-chapter-functions-drawer")).toBeVisible();
    const m = await measureHarnessLayout(page);
    expect(m.scrollWidth).toBeLessThanOrEqual(m.clientWidth + 1);
    expect(m.hasPurchase).toBeFalsy();
  });
});

test.describe("WB-2.2 free page regression smoke (no final CF wiring)", () => {
  test("overview / characters-events / structure still work; CF nav available badge", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installFreePageMocks(page);
    await page.goto(`/books/${BOOK_ID}/whole-book`);
    await expect(page.getByTestId("whole-book-free-product-page")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-overview")).toBeVisible();

    await page.getByTestId("whole-book-free-module-characters_events").click();
    await expect(page.getByTestId("whole-book-free-characters-events")).toBeVisible();

    await page.getByTestId("whole-book-free-module-structure").click();
    await expect(page.getByTestId("whole-book-free-structure")).toHaveAttribute(
      "data-state",
      "available",
    );

    // Module table available — final panel wiring still PlannedModulePanel (Integration).
    await expect(page.getByTestId("whole-book-free-module-chapter_functions")).not.toContainText(
      "开发中",
    );
    await page.getByTestId("whole-book-free-module-chapter_functions").click();
    await expect(page.getByTestId("whole-book-free-chapter-functions-planned")).toBeVisible();

    const body = await page.evaluate(() => document.body.innerText);
    expect(/购买|升级\s*Pro|立即开通/.test(body)).toBeFalsy();
  });
});
