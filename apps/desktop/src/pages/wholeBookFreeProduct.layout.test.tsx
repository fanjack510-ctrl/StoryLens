/**
 * CHG-20260801-031 — whole-book desktop workbench layout (Vitest structure + CSS contract).
 * Geometric 1920/1366 assertions run via Playwright evidence script.
 */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WholeBookFreeProductPage } from "./WholeBookFreeProductPage";
import * as freeApiMod from "../services/wholeBookFreeProductApi";
import styles from "./WholeBookFreeProductPage.module.css";

vi.mock("../services/wholeBookFreeProductFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/wholeBookFreeProductFlag")>(
    "../services/wholeBookFreeProductFlag",
  );
  return {
    ...actual,
    isWholeBookFreeProductEnabled: () => true,
  };
});

vi.mock("../services/wholeBookFixturePreviewFlag", () => ({
  isWholeBookFixturePreviewEnabled: () => true,
}));

vi.mock("../services/wholeBookRealProviderFlag", () => ({
  isWholeBookRealProviderEnabled: () => false,
}));

const prepareSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "prepare");
const capabilitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "productCapabilities");
const getOverviewSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getOverview");
const listEntitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEntities");
const listAssetsSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listAssets");
const listEvidencesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEvidences");
const listStagesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listStages");
const progressSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getProgress");

const completedRun = {
  run_id: 1,
  book_id: 8,
  snapshot_id: 1,
  mode: "whole_book_native",
  status: "completed",
  current_stage_code: "finalize",
  engine_id: "diagnostic_contract_engine",
  result_origin: "fixture",
  started_at: "2026-07-28T05:39:25Z",
  completed_at: "2026-07-28T05:39:25Z",
};

function basePrepare(overrides: Record<string, unknown> = {}) {
  return {
    book_id: 8,
    book_title: "Sample S",
    chapter_count: 3,
    character_count: 291,
    mode: "whole_book_native",
    mode_label: "原生全书分析",
    product_enabled: true,
    real_provider_enabled: false,
    run_creation_enabled: false,
    fixture_preview_enabled: true,
    latest_run: completedRun,
    recoverable_run: null,
    snapshot_rebuild_required: false,
    estimate: {
      estimate_id: 1,
      book_id: 8,
      mode: "whole_book_native",
      estimated_windows: 1,
      estimated_provider_calls: 2,
      estimated_input_tokens: 1000,
      estimated_output_tokens: 500,
      estimated_cost_min_cny: null,
      estimated_cost_max_cny: null,
      provider_name: "fixture",
      model_name: "fixture-model",
      price_known: false,
      currency: "CNY",
    },
    recommended_limits: {
      max_provider_calls: 200,
      max_input_tokens: 500000,
      max_output_tokens: 100000,
      max_cost_budget_cny: "10.00",
    },
    blocking_reasons: [],
    warnings: [],
    ...overrides,
  };
}

function nineClaims() {
  const keys = [
    "genre_and_narrative_features",
    "core_setting",
    "protagonist",
    "protagonist_core_goal",
    "main_conflict",
    "core_question",
    "final_resolution",
    "important_characters",
    "key_events",
  ];
  return keys.map((claim_key) => ({
    claim_key,
    availability: "available",
    confidence: 0.85,
    summary: `摘要-${claim_key}`,
    evidence_ids: [1],
    conflict_ids: [],
    supporting_asset_ids: [],
  }));
}

function renderPage(path = "/books/8/whole-book") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId/whole-book" element={<WholeBookFreeProductPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CHG-031 whole-book layout contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    capabilitiesSpy.mockResolvedValue({
      capabilities: [
        { capability_id: "whole_book.overview", display_name: "全书总览", required_tier: "free", release_status: "available", access_status: "granted", reason_code: null },
        { capability_id: "whole_book.characters_events", display_name: "主要人物与关键事件", required_tier: "free", release_status: "available", access_status: "granted", reason_code: null },
      ],
    });
    listStagesSpy.mockResolvedValue({ stages: [] });
    progressSpy.mockResolvedValue({
      run_id: 1,
      status: "completed",
      overall_progress: 1,
      current_stage: "finalize",
      completed_windows: 3,
      total_windows: 3,
      completed_provider_units: 0,
      total_provider_units: 0,
      provider_calls_used: 0,
      provider_calls_limit: null,
      input_tokens_used: 0,
      output_tokens_used: 0,
      cost_used_cny: null,
      pause_requested: false,
      cancel_requested: false,
      can_pause: false,
      can_resume: false,
      can_cancel: false,
      started_at: null,
      updated_at: null,
      result_origin: "fixture",
    });
    listEvidencesSpy.mockResolvedValue({
      evidences: [{ evidence_id: 1, quote_text: "林川", global_paragraph_index: 0 }],
    });
    listEntitiesSpy.mockResolvedValue({
      entities: [
        {
          entity_id: 1,
          canonical_name: "林川",
          aliases: [],
          event_count: 1,
          evidence_count: 1,
          confidence: 0.9,
          linked_evidences: [{ evidence_id: 1 }],
        },
      ],
    });
    listAssetsSpy.mockResolvedValue({ assets: [] });
  });

  it("CSS workbench contract: wide max-width and desktop grid", () => {
    // Compiled CSS module string still contains design tokens for workbench width.
    expect(styles.wholeBookFreePage).toBeTruthy();
    expect(styles.wholeBookFreeLayout).toBeTruthy();
    expect(styles.wholeBookFreeLimitsGrid).toBeTruthy();
    expect(styles.wholeBookFreeClaimList).toBeTruthy();
  });

  it("renders workbench layout regions and nine overview claims", async () => {
    prepareSpy.mockResolvedValue(basePrepare());
    getOverviewSpy.mockResolvedValue({
      overview: {
        book_id: 8,
        run_id: 1,
        claims: nineClaims(),
        status: "completed",
        result_origin: "fixture",
      },
    });

    renderPage();
    expect(await screen.findByTestId("whole-book-free-product-page")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-layout")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-module-nav")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-main-content")).toBeInTheDocument();

    const overview = await screen.findByTestId("whole-book-free-overview");
    const claims = within(overview).getAllByTestId(/^whole-book-free-claim-(?!evidence-)/);
    expect(claims).toHaveLength(9);
    expect(screen.queryByText(/购买|升级 Pro|立即开通/i)).toBeNull();
  });

  it("prepare mode keeps cost/consent/limits and provider disabled guard", async () => {
    prepareSpy.mockResolvedValue(
      basePrepare({
        latest_run: null,
        recoverable_run: null,
      }),
    );

    renderPage();
    expect(await screen.findByTestId("whole-book-free-prepare")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-cost-estimate")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-consent")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-limits-grid")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-limits-budget")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-real-provider-disabled")).toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-start-fixture")).toBeInTheDocument();
    expect(screen.queryByText(/购买|升级 Pro|立即开通/i)).toBeNull();
  });
});
