/**
 * WB-2.1 / CHG-20260801-035 — structure stages Free product UI (Vitest).
 * Uses TEST-ONLY fixtures; no formal DB / real provider.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WholeBookFreeProductPage } from "./WholeBookFreeProductPage";
import * as freeApiMod from "../services/wholeBookFreeProductApi";
import { WHOLE_BOOK_FREE_MODULES } from "../services/wholeBookFreeProductApi";
import { openEvidenceInReader } from "../services/wholeBookFreeEvidenceDeepLink";
import { adaptStructureStagesV1ToV2 } from "../services/structureStagesV1Adapter";
import {
  assertStructureStagesResultV2,
  UnsupportedStructureContractError,
} from "../services/structureStagesResultV2";
import {
  STRUCTURE_UI_FIXTURES,
  FIXTURE_K_V1_LAB,
  productEnvelope,
  FIXTURE_A_AVAILABLE_MULTI,
  FIXTURE_B_NON_THREE_ACT,
  FIXTURE_C_VARIABLE_COUNT,
  FIXTURE_D_TP_EMPTY,
} from "../components/wholeBookFree/structure/fixtures/structureUiFixtures";
import type { EvidenceSourceDetail, WholeBookRunRecord } from "../services/wholeBookFreeProductApi";

vi.mock("../services/wholeBookFreeProductFlag", () => ({
  isWholeBookFreeProductEnabled: () => true,
}));
vi.mock("../services/wholeBookFixturePreviewFlag", () => ({
  isWholeBookFixturePreviewEnabled: () => false,
}));
vi.mock("../services/wholeBookRealProviderFlag", () => ({
  isWholeBookRealProviderEnabled: () => false,
}));

const prepareSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "prepare");
const getOverviewSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getOverview");
const listEntitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEntities");
const listAssetsSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listAssets");
const listEvidencesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listEvidences");
const listStagesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "listStages");
const getStructureSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getStructure");
const getEvidenceSourceSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getEvidenceSource");
const capabilitiesSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "productCapabilities");
const progressSpy = vi.spyOn(freeApiMod.wholeBookFreeProductApi, "getProgress");

function baseRun(status = "completed", overrides: Partial<WholeBookRunRecord> = {}): WholeBookRunRecord {
  return {
    run_id: 42,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    status,
    current_stage_code: null,
    idempotency_key: "k1",
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
    created_at: "2026-07-28T00:00:00Z",
    started_at: "2026-07-28T00:01:00Z",
    paused_at: null,
    completed_at: status === "completed" ? "2026-07-28T01:00:00Z" : null,
    failed_at: status === "failed" ? "2026-07-28T01:00:00Z" : null,
    cancelled_at: status === "cancelled" ? "2026-07-28T01:00:00Z" : null,
    failure_code: status === "failed" ? "STRUCTURE_EMPTY_RESULT_AFTER_REPAIR" : null,
    failure_message_safe: status === "failed" ? "结构失败" : null,
    ...overrides,
  };
}

function basePrepare(run: WholeBookRunRecord | null) {
  return {
    book_id: 1,
    book_title: "测试书",
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
  } satisfies freeApiMod.WholeBookPrepareResponse;
}

function baseOverview() {
  return {
    result_version: "v1",
    contract_version: "whole_book_contract_v1",
    run_id: 42,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    result_origin: "fixture",
    status: "completed" as const,
    important_entity_ids: [],
    key_event_asset_ids: [],
    warnings: [],
    created_at: "2026-07-28T01:00:00Z",
    claims: [],
  };
}

function evidenceSource(): EvidenceSourceDetail {
  return {
    evidence_id: 501,
    chapter_id: 42,
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
    snapshot_id: 11,
    state: "valid",
  };
}

function renderPage(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId/whole-book" element={<WholeBookFreeProductPage />} />
          <Route path="/books/:bookId" element={<div data-testid="book-shell-toolbar">reader</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function openStructure() {
  fireEvent.click(await screen.findByTestId("whole-book-free-module-structure"));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  capabilitiesSpy.mockResolvedValue({ capabilities: [] });
  listStagesSpy.mockResolvedValue({ stages: [] });
  progressSpy.mockResolvedValue({
    run_id: 42,
    status: "running",
    overall_progress: 0.4,
    current_stage: "synthesize_structure_stages",
    completed_windows: 1,
    total_windows: 2,
    completed_provider_units: 1,
    total_provider_units: 2,
    provider_calls_used: 1,
    provider_calls_limit: 200,
    input_tokens_used: 10,
    output_tokens_used: 5,
    cost_used_cny: null,
    pause_requested: false,
    cancel_requested: false,
    can_pause: true,
    can_resume: false,
    can_cancel: true,
    started_at: "2026-07-28T00:01:00Z",
    updated_at: "2026-07-28T00:02:00Z",
    result_origin: "fixture",
  });
  getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
  listEntitiesSpy.mockResolvedValue({ entities: [] });
  listAssetsSpy.mockResolvedValue({ assets: [], total: 0, offset: 0, limit: 50 });
  listEvidencesSpy.mockResolvedValue({ evidences: [] });
  getEvidenceSourceSpy.mockResolvedValue({ source: evidenceSource() });
});

describe("WB-2.1 structure module shell", () => {
  it("flips structure from planned to available; free modules remain 4; chapter_functions available", () => {
    const free = WHOLE_BOOK_FREE_MODULES.filter((m) => m.status !== "pro_planned");
    expect(free).toHaveLength(4);
    expect(WHOLE_BOOK_FREE_MODULES.find((m) => m.key === "structure")?.status).toBe("available");
    expect(WHOLE_BOOK_FREE_MODULES.find((m) => m.key === "chapter_functions")?.status).toBe(
      "available",
    );
    expect(WHOLE_BOOK_FREE_MODULES.filter((m) => m.status === "pro_planned")).toHaveLength(1);
  });

  it("renders available multi-stage structure without purchase UI", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(STRUCTURE_UI_FIXTURES.A_available_multi);
    renderPage("/books/1/whole-book");
    await openStructure();
    expect(await screen.findByTestId("whole-book-free-structure")).toHaveAttribute(
      "data-state",
      "available",
    );
    expect(screen.getByTestId("whole-book-free-structure-stage-list").children.length).toBe(3);
    expect(screen.getByTestId("whole-book-free-structure-tp-TP1")).toBeInTheDocument();
    expect(screen.queryByText("第一幕")).not.toBeInTheDocument();
    expect(screen.queryByText("购买")).not.toBeInTheDocument();
    expect(screen.getByTestId("whole-book-free-module-chapter_functions")).not.toHaveTextContent(
      "开发中",
    );
  });

  it("supports non-three-act and variable stage counts", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(productEnvelope(FIXTURE_B_NON_THREE_ACT));
    renderPage("/books/1/whole-book?module=structure");
    const listB = await screen.findByTestId("whole-book-free-structure-stage-list");
    expect(listB.children.length).toBe(4);
    expect(screen.getByText("抵达")).toBeInTheDocument();
    expect(screen.queryByText("第三幕")).not.toBeInTheDocument();

    cleanup();
    getStructureSpy.mockResolvedValue(productEnvelope(FIXTURE_C_VARIABLE_COUNT));
    renderPage("/books/1/whole-book?module=structure");
    const listC = await screen.findByTestId("whole-book-free-structure-stage-list");
    expect(listC.children.length).toBe(1);
  });

  it("shows empty turning points message without treating as error", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(productEnvelope(FIXTURE_D_TP_EMPTY));
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-tp-empty")).toHaveTextContent(
      "未识别出足够明确的独立转折点",
    );
    expect(screen.getByTestId("whole-book-free-structure")).toHaveAttribute("data-state", "available");
    expect(screen.queryByTestId("whole-book-free-structure-failed")).not.toBeInTheDocument();
  });

  it("renders insufficient empty state", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(STRUCTURE_UI_FIXTURES.E_insufficient);
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-insufficient-message")).toHaveTextContent(
      "当前原文覆盖或证据不足，暂无法可靠识别全书结构阶段。",
    );
    expect(screen.getByTestId("whole-book-free-structure-empty-reason")).toHaveTextContent(
      "INSUFFICIENT_TEXT_VOLUME",
    );
    expect(screen.queryByTestId("whole-book-free-structure-stage-list")).not.toBeInTheDocument();
  });

  it("renders failed / canceled / conflict / loading / absent", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("failed")));
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-failed")).toBeInTheDocument();

    cleanup();
    prepareSpy.mockResolvedValue(basePrepare(baseRun("cancelled")));
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-canceled")).toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-free-structure-failed")).not.toBeInTheDocument();

    cleanup();
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(STRUCTURE_UI_FIXTURES.H_conflict);
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-conflict")).toBeInTheDocument();

    cleanup();
    prepareSpy.mockResolvedValue(basePrepare(baseRun("running")));
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-loading")).toBeInTheDocument();

    cleanup();
    const { ApiError } = await import("../services/apiClient");
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockRejectedValue(
      new ApiError("STRUCTURE_RESULT_ABSENT", "absent", 404, {
        error_code: "STRUCTURE_RESULT_ABSENT",
      }),
    );
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure-absent")).toHaveTextContent(
      "尚未生成故事结构结果",
    );
    expect(screen.queryByText("无数据")).not.toBeInTheDocument();
  });

  it("rejects unsupported contract version and adapts V1 for Lab only", () => {
    expect(() => assertStructureStagesResultV2(STRUCTURE_UI_FIXTURES.L_unsupported_raw)).toThrow(
      UnsupportedStructureContractError,
    );
    const adapted = adaptStructureStagesV1ToV2(FIXTURE_K_V1_LAB);
    expect(adapted.contract_version).toBe("v2");
    expect(adapted.stages).toHaveLength(2);
    expect(adapted.limitations).toContain("V1_ADAPTER_ONLY");
  });

  it("opens evidence deep link with exact offsets and keeps structure module on return", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(STRUCTURE_UI_FIXTURES.A_available_multi);
    renderPage("/books/1/whole-book?module=structure");
    await screen.findByTestId("whole-book-free-structure-stage-S1");
    fireEvent.click(screen.getByTestId("whole-book-free-structure-stage-evidence-S1"));
    expect(await screen.findByTestId("whole-book-free-evidence-drawer")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("whole-book-free-open-in-reader"));
    await waitFor(() => expect(screen.getByTestId("book-shell-toolbar")).toBeInTheDocument());

    const href = openEvidenceInReader(1, evidenceSource(), 42, { returnModule: "structure" });
    expect(href).toContain("chapter=42");
    expect(href).toContain("chapterId=42");
    expect(href).toContain("paragraphIndex=3");
    expect(href).toContain("startOffset=1");
    expect(href).toContain("endOffset=5");
    expect(href).toContain("returnModule=structure");
    expect(href).not.toContain("evidence_map");
    // chapter_index is display-only, never used as chapter id
    expect(href).toContain("chapterIndex=1");
    expect(href).not.toMatch(/[?&]chapter=1(?:&|$)/);

    cleanup();
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(STRUCTURE_UI_FIXTURES.A_available_multi);
    renderPage("/books/1/whole-book?module=structure");
    expect(await screen.findByTestId("whole-book-free-structure")).toHaveAttribute(
      "data-state",
      "available",
    );
    expect(screen.getByTestId("whole-book-free-module-structure")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("does not regress overview / characters modules", async () => {
    prepareSpy.mockResolvedValue(basePrepare(baseRun("completed")));
    getStructureSpy.mockResolvedValue(productEnvelope(FIXTURE_A_AVAILABLE_MULTI));
    renderPage("/books/1/whole-book");
    expect(await screen.findByTestId("whole-book-free-overview")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("whole-book-free-module-characters_events"));
    expect(await screen.findByTestId("whole-book-free-characters-events")).toBeInTheDocument();
  });
});
