/**
 * WB-2.1 / CHG-20260801-035 — Playwright structure stages UI.
 * TEST DATA ONLY via route mocks. No real provider / formal DB writes.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

const BOOK_ID = 1;
const RUN_ID = 42;

const STRUCTURE_AVAILABLE = {
  result_status: "completed",
  coverage_scope: "full_selected_range",
  structure: {
    contract_version: "v2",
    evidence_contract_version: "v2",
    coverage_scope: "full_selected_range",
    analysis_confidence: 0.86,
    overall_confidence: 0.86,
    limitations: [],
    context_capabilities: { can_identify_local_stages: true },
    stages: [
      {
        local_stage_ref: "S1",
        order_index: 0,
        stage_type: "setup",
        title: "开局承压",
        summary: {
          value: "主角进入陌生环境并接受试炼。",
          status: "observed",
          citation_ids: ["CIT-TEST0001-0001"],
          confidence: 0.84,
        },
        start_boundary: { citation_ids: ["CIT-TEST0001-0001"], value: "ch1" },
        end_boundary: { citation_ids: ["CIT-TEST0001-0002"], value: "ch3" },
        confidence: 0.84,
        chapter_range: [1, 3],
      },
      {
        local_stage_ref: "S2",
        order_index: 1,
        stage_type: "rising",
        title: "对抗升级",
        summary: {
          value: "冲突扩大。",
          status: "observed",
          citation_ids: ["CIT-TEST0001-0003"],
          confidence: 0.8,
        },
        start_boundary: { citation_ids: ["CIT-TEST0001-0003"], value: "ch4" },
        end_boundary: { citation_ids: ["CIT-TEST0001-0004"], value: "ch8" },
        confidence: 0.8,
        chapter_range: [4, 8],
      },
      {
        local_stage_ref: "S3",
        order_index: 2,
        stage_type: "climax",
        title: "决断时刻",
        summary: {
          value: "做出不可逆选择。",
          status: "inferred",
          citation_ids: ["CIT-TEST0001-0005"],
          confidence: 0.78,
        },
        start_boundary: { citation_ids: ["CIT-TEST0001-0005"], value: "ch9" },
        end_boundary: { citation_ids: ["CIT-TEST0001-0006"], value: "ch12" },
        confidence: 0.78,
        chapter_range: [9, 12],
      },
    ],
    turning_points: [
      {
        local_turning_point_ref: "TP1",
        title: "身份暴露",
        turning_point_type: "reveal",
        description: {
          value: "关键秘密被揭开。",
          status: "observed",
          citation_ids: ["CIT-TEST0001-0003"],
          confidence: 0.77,
        },
        citation_ids: ["CIT-TEST0001-0003"],
        chapter_id: 4,
        confidence: 0.77,
      },
    ],
  },
  source_revision: { run_id: RUN_ID, snapshot_id: 11, snapshot_revision: "rev-e2e" },
  citation_evidence_bindings: [
    { citation_id: "CIT-TEST0001-0001", evidence_id: 501 },
    { citation_id: "CIT-TEST0001-0003", evidence_id: 503 },
  ],
};

const STRUCTURE_INSUFFICIENT = {
  result_status: "completed",
  coverage_scope: "insufficient",
  empty_reason: "INSUFFICIENT_TEXT_VOLUME",
  structure: {
    contract_version: "v2",
    evidence_contract_version: "v2",
    coverage_scope: "insufficient",
    stages: [],
    turning_points: [],
    limitations: ["INSUFFICIENT_TEXT_VOLUME"],
    context_capabilities: { can_identify_local_stages: false },
  },
  citation_evidence_bindings: [],
};

function completedRun() {
  return {
    run_id: RUN_ID,
    book_id: BOOK_ID,
    snapshot_id: 11,
    mode: "whole_book_native",
    status: "completed",
    current_stage_code: "finalize",
    idempotency_key: "e2e",
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
    created_at: "2026-08-01T00:00:00Z",
    started_at: "2026-08-01T00:01:00Z",
    paused_at: null,
    completed_at: "2026-08-01T01:00:00Z",
    failed_at: null,
    cancelled_at: null,
    failure_code: null,
    failure_message_safe: null,
  };
}

function prepareBody(run = completedRun()) {
  return {
    book_id: BOOK_ID,
    book_title: "E2E Structure Book",
    chapter_count: 12,
    character_count: 120000,
    mode: "whole_book_native",
    mode_label: "原生全书分析",
    product_enabled: true,
    real_provider_enabled: false,
    run_creation_enabled: false,
    fixture_preview_enabled: false,
    latest_run: run,
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

async function installMocks(page: Page, structureBody: unknown = STRUCTURE_AVAILABLE) {
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
    if (url.includes(`/books/${BOOK_ID}/whole-book/prepare`) || url.includes(`/books/${BOOK_ID}/whole-book/free/prepare`)) {
      return json(route, prepareBody());
    }
    if (url.includes(`/whole-book/runs/${RUN_ID}/structure`)) {
      return json(route, structureBody);
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
          created_at: "2026-08-01T01:00:00Z",
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
    if (url.includes("/whole-book/evidences/501/source")) {
      return json(route, {
        source: {
          evidence_id: 501,
          chapter_title: "第1章",
          chapter_index: 1,
          paragraph_index: 3,
          global_paragraph_index: 3,
          paragraph_text: "他踏入山门，看见试炼石碑。",
          quote_text: "踏入山门",
          start_offset: 1,
          end_offset: 5,
          quote_hash: "qh",
          paragraph_text_hash: "ph",
          state: "valid",
        },
      });
    }
    if (url.includes(`/books/${BOOK_ID}`) && !url.includes("whole-book")) {
      return json(route, { id: BOOK_ID, title: "E2E Structure Book" });
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

async function measureLayout(page: Page) {
  return page.evaluate(() => {
    const root = document.querySelector('[data-testid="whole-book-free-product-page"]');
    const nav = document.querySelector('[data-testid="whole-book-free-module-nav"]');
    const main = document.querySelector('[data-testid="whole-book-free-main-content"]');
    const stages = [...document.querySelectorAll('[data-testid^="whole-book-free-structure-stage-S"]')];
    return {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
      navWidth: nav ? (nav as HTMLElement).offsetWidth : 0,
      mainWidth: main ? (main as HTMLElement).offsetWidth : 0,
      rootMaxWidth: root ? getComputedStyle(root).maxWidth : null,
      stageCount: stages.length,
      hasPurchase: /购买|升级\s*Pro|立即开通/.test(document.body.innerText),
      bodyText: document.body.innerText,
    };
  });
}

test.describe("WB-2.1 structure stages desktop", () => {
  test("1920×1080 available multi-stage + evidence + no purchase + no h-scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await installMocks(page, STRUCTURE_AVAILABLE);
    await page.goto(`/books/${BOOK_ID}/whole-book`);
    await expect(page.getByTestId("whole-book-free-product-page")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-overview")).toBeVisible();

    await page.getByTestId("whole-book-free-module-structure").click();
    await expect(page.getByTestId("whole-book-free-structure")).toHaveAttribute("data-state", "available");
    await expect(page.getByTestId("whole-book-free-structure-stage-list")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-structure-stage-S1")).toContainText("开局承压");
    await expect(page.getByTestId("whole-book-free-structure-stage-S3")).toBeVisible();
    await expect(page.getByText("第一幕")).toHaveCount(0);

    await page.getByTestId("whole-book-free-structure-stage-evidence-S1").click();
    await expect(page.getByTestId("whole-book-free-evidence-drawer")).toBeVisible();
    await page.getByTestId("whole-book-free-open-in-reader").click();
    await expect(page).toHaveURL(/chapter=1/);
    await expect(page).toHaveURL(/paragraphIndex=3/);
    await expect(page).toHaveURL(/startOffset=1/);
    await expect(page).toHaveURL(/endOffset=5/);
    await expect(page).toHaveURL(/returnModule=structure/);

    // Re-enter Free structure module (returnModule contract); avoid full BookRoute shell deps.
    await page.goto(`/books/${BOOK_ID}/whole-book?module=structure`);
    await expect(page.getByTestId("whole-book-free-structure")).toHaveAttribute("data-state", "available");
    await expect(page.getByTestId("whole-book-free-module-structure")).toHaveAttribute("data-active", "true");

    await page.reload();
    await expect(page.getByTestId("whole-book-free-structure")).toHaveAttribute("data-state", "available");

    await page.getByTestId("whole-book-free-module-overview").click();
    await expect(page.getByTestId("whole-book-free-overview")).toBeVisible();
    await page.getByTestId("whole-book-free-module-characters_events").click();
    await expect(page.getByTestId("whole-book-free-characters-events")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-module-chapter_functions")).not.toContainText(
      "开发中",
    );

    const m = await measureLayout(page);
    expect(m.hasPurchase).toBeFalsy();
    expect(m.scrollWidth).toBeLessThanOrEqual(m.clientWidth + 1);
    expect(m.navWidth).toBeGreaterThanOrEqual(200);
  });

  test("1366×768 single-column stages + insufficient empty + no h-scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 768 });
    await installMocks(page, STRUCTURE_INSUFFICIENT);
    await page.goto(`/books/${BOOK_ID}/whole-book?module=structure`);
    await expect(page.getByTestId("whole-book-free-structure-insufficient")).toBeVisible();
    await expect(page.getByTestId("whole-book-free-structure-insufficient-message")).toContainText(
      "当前原文覆盖或证据不足",
    );
    const m = await measureLayout(page);
    expect(m.scrollWidth).toBeLessThanOrEqual(m.clientWidth + 1);
    expect(m.hasPurchase).toBeFalsy();
    expect(m.bodyText).not.toContain("第一幕");
  });
});
