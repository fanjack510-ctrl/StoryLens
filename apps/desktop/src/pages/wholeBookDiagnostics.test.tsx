import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WholeBookDiagnosticsPage } from "./WholeBookDiagnosticsPage";
import { AppShell } from "../components/layout/AppShell";
import * as foundationApiMod from "../services/wholeBookFoundationApi";
import type {
  BookOverviewResultRow,
  BookSnapshotMetadata,
  EvidenceSourceDetail,
  GenerateWindowsResponse,
  MinimalAnalysisSummary,
  NarrativeAssetRow,
  NarrativeEntityRow,
  NarrativeEvidenceRow,
  WholeBookRunRecord,
  WholeBookRunStageRow,
  WholeBookWindowCoverage,
} from "../services/wholeBookFoundationApi";

const flagState = vi.hoisted(() => ({ enabled: true }));

vi.mock("../services/wholeBookDiagnosticsFlag", async () => {
  const actual = await vi.importActual<typeof import("../services/wholeBookDiagnosticsFlag")>(
    "../services/wholeBookDiagnosticsFlag",
  );
  return {
    ...actual,
    isWholeBookDiagnosticsEnabled: () => flagState.enabled,
  };
});

vi.mock("../components/onboarding/QwenFirstLaunchBanner", () => ({
  QwenFirstLaunchBanner: () => null,
}));

vi.mock("../components/onboarding/FirstLaunchWizard", () => ({
  FirstLaunchWizard: () => null,
}));

const createSnapshotSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "createSnapshot");
const createRunSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "createRun");
const listStagesSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "listStages");
const getRunSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "getRun");
const generateWindowsSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "generateWindows");
const executeMinimalFixtureSpy = vi.spyOn(
  foundationApiMod.wholeBookFoundationApi,
  "executeMinimalAnalysisFixture",
);
const getMinimalSummarySpy = vi.spyOn(
  foundationApiMod.wholeBookFoundationApi,
  "getMinimalAnalysisSummary",
);
const listEntitiesSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "listEntities");
const listAssetsSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "listAssets");
const listEvidencesSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "listEvidences");
const getOverviewSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "getOverview");
const getEvidenceSourceSpy = vi.spyOn(
  foundationApiMod.wholeBookFoundationApi,
  "getEvidenceSource",
);

const booksList = vi.fn();
const booksChapters = vi.fn();

vi.mock("../services/booksApi", async () => {
  const actual = await vi.importActual<typeof import("../services/booksApi")>("../services/booksApi");
  return {
    ...actual,
    booksApi: {
      ...actual.booksApi,
      list: (...args: unknown[]) => booksList(...args),
      chapters: (...args: unknown[]) => booksChapters(...args),
    },
  };
});

function baseSnapshot(overrides: Partial<BookSnapshotMetadata> = {}): BookSnapshotMetadata {
  return {
    snapshot_id: 11,
    book_id: 1,
    snapshot_version: 1,
    status: "completed",
    content_hash: "abc123hash",
    chapter_count: 2,
    paragraph_count: 20,
    character_count: 5000,
    created_at: "2026-07-28T00:00:00Z",
    completed_at: "2026-07-28T00:00:01Z",
    ...overrides,
  };
}

function baseRun(status = "pending", overrides: Partial<WholeBookRunRecord> = {}): WholeBookRunRecord {
  return {
    run_id: 21,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    status,
    current_stage_code: "windowing",
    idempotency_key: "idem-1",
    engine_id: "diagnostic_contract_engine",
    engine_version: "1",
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
    started_at: null,
    paused_at: null,
    completed_at: null,
    failed_at: null,
    cancelled_at: null,
    failure_code: null,
    failure_message_safe: null,
    ...overrides,
  };
}

function baseStages(): WholeBookRunStageRow[] {
  return [
    {
      stage_id: 1,
      run_id: 21,
      stage_code: "snapshot",
      sequence: 0,
      status: "completed",
      progress_current: 1,
      progress_total: 1,
      started_at: "2026-07-28T00:00:00Z",
      completed_at: "2026-07-28T00:00:00Z",
      last_error_code: null,
      last_error_message_safe: null,
    },
    {
      stage_id: 2,
      run_id: 21,
      stage_code: "windowing",
      sequence: 1,
      status: "pending",
      progress_current: 0,
      progress_total: 0,
      started_at: null,
      completed_at: null,
      last_error_code: null,
      last_error_message_safe: null,
    },
  ];
}

function baseCoverage(): WholeBookWindowCoverage {
  return {
    snapshot_id: 11,
    run_id: 21,
    total_paragraphs: 20,
    covered_unique_paragraphs: 20,
    duplicated_paragraphs: 2,
    uncovered_paragraphs: 0,
    coverage_ratio: 1,
    order_valid: true,
    first_global_paragraph_index: 0,
    last_global_paragraph_index: 19,
  };
}

function baseMinimalSummary(overrides: Partial<MinimalAnalysisSummary> = {}): MinimalAnalysisSummary {
  return {
    run_id: 21,
    status: "completed",
    current_stage_code: "synthesize_overview",
    completed_windows: 2,
    total_windows: 2,
    entity_count: 1,
    asset_count: 2,
    evidence_count: 2,
    relation_count: 1,
    provider_fixture_call_count: 2,
    provider_real_call_count: 0,
    overview_status: "completed",
    ...overrides,
  };
}

function baseEntities(): NarrativeEntityRow[] {
  return [
    {
      entity_id: 101,
      entity_type: "character",
      canonical_name: "林远",
      aliases: [
        { name: "小林", confidence: 0.9, evidence_ids: [501] },
        { name: "远哥", confidence: 0.85, evidence_ids: [502] },
      ],
      state: "candidate",
      confidence: 0.92,
      evidence_count: 2,
      event_count: 1,
      character_profile: {
        asset_id: 201,
        asset_type: "character_profile",
        title: "林远档案",
        summary: "主角，谨慎务实。",
        state: "candidate",
        confidence: 0.9,
        evidence_count: 1,
        subject_entity_ids: [101],
      },
      goals: [
        {
          asset_id: 202,
          asset_type: "goal",
          title: "查明真相",
          state: "candidate",
          confidence: 0.88,
          evidence_count: 1,
          subject_entity_ids: [101],
        },
      ],
      events: [
        {
          asset_id: 301,
          asset_type: "event",
          title: "夜探旧库",
          state: "candidate",
          confidence: 0.86,
          evidence_count: 1,
          subject_entity_ids: [101],
          event_type: "discovery",
          chapters: [1],
          participants: ["林远"],
        },
      ],
      linked_evidences: [
        {
          evidence_id: 501,
          state: "valid",
          confidence: 0.9,
          quote_text: "林远",
        },
      ],
    },
  ];
}

function baseEventAssets(): NarrativeAssetRow[] {
  return [
    {
      asset_id: 301,
      asset_type: "event",
      title: "夜探旧库",
      state: "candidate",
      confidence: 0.86,
      evidence_count: 1,
      subject_entity_ids: [101],
      event_type: "discovery",
      chapters: [1],
      participants: ["林远"],
    },
  ];
}

function baseEvidences(): NarrativeEvidenceRow[] {
  return [
    {
      evidence_id: 501,
      state: "valid",
      confidence: 0.9,
      chapter_index: 1,
      paragraph_index: 2,
      global_paragraph_index: 12,
      quote_text: "林远",
    },
    {
      evidence_id: 502,
      state: "valid",
      confidence: 0.85,
      chapter_index: 1,
      paragraph_index: 3,
      global_paragraph_index: 13,
      quote_text: "旧库",
    },
  ];
}

function baseEvidenceSource(): EvidenceSourceDetail {
  return {
    evidence_id: 501,
    chapter_id: 7,
    chapter_title: "第1章",
    chapter_index: 1,
    paragraph_index: 2,
    global_paragraph_index: 12,
    paragraph_text: "夜里，林远独自来到旧库门前。",
    quote_text: "林远",
    start_offset: 3,
    end_offset: 5,
    quote_hash: "qh1",
    paragraph_text_hash: "ph1",
    snapshot_id: 11,
    state: "valid",
  };
}

function baseOverview(): BookOverviewResultRow {
  return {
    result_version: "book_overview_v1",
    contract_version: "whole_book_contract_v1",
    run_id: 21,
    book_id: 1,
    snapshot_id: 11,
    mode: "whole_book_native",
    result_origin: "fixture",
    status: "partial",
    important_entity_ids: [101],
    key_event_asset_ids: [301],
    warnings: [],
    created_at: "2026-07-28T01:00:00Z",
    claims: [
      {
        claim_key: "genre_and_narrative_features",
        availability: "available",
        summary: "都市悬疑。",
        confidence: 0.8,
        evidence_ids: [501],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "core_setting",
        availability: "available",
        summary: "现代城市。",
        confidence: 0.75,
        evidence_ids: [502],
        supporting_asset_ids: [401],
        conflict_ids: [],
      },
      {
        claim_key: "protagonist",
        availability: "available",
        summary: "林远。",
        confidence: 0.9,
        evidence_ids: [501],
        supporting_asset_ids: [201],
        conflict_ids: [],
      },
      {
        claim_key: "protagonist_core_goal",
        availability: "insufficient_evidence",
        summary: "目标线索不足。",
        confidence: null,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "main_conflict",
        availability: "available",
        summary: "真相与隐瞒。",
        confidence: 0.7,
        evidence_ids: [502],
        supporting_asset_ids: [402],
        conflict_ids: [],
      },
      {
        claim_key: "core_question",
        availability: "available",
        summary: "旧库藏着什么？",
        confidence: 0.72,
        evidence_ids: [502],
        supporting_asset_ids: [403],
        conflict_ids: [],
      },
      {
        claim_key: "final_resolution",
        availability: "unavailable",
        summary: null,
        confidence: null,
        evidence_ids: [],
        supporting_asset_ids: [],
        conflict_ids: [],
      },
      {
        claim_key: "important_characters",
        availability: "available",
        summary: "林远等。",
        confidence: 0.8,
        evidence_ids: [501],
        supporting_asset_ids: [201],
        conflict_ids: [],
      },
      {
        claim_key: "key_events",
        availability: "available",
        summary: "夜探旧库。",
        confidence: 0.86,
        evidence_ids: [501],
        supporting_asset_ids: [301],
        conflict_ids: [],
      },
    ],
  };
}

function mockMinimalAnalysisApis() {
  getRunSpy.mockResolvedValue({ run: baseRun("completed", { current_stage_code: "finalize" }) });
  listStagesSpy.mockResolvedValue({ stages: baseStages() });
  executeMinimalFixtureSpy.mockResolvedValue({
    run: baseRun("completed", { current_stage_code: "finalize" }),
    summary: baseMinimalSummary(),
  });
  getMinimalSummarySpy.mockResolvedValue({ summary: baseMinimalSummary() });
  listEntitiesSpy.mockResolvedValue({ entities: baseEntities() });
  listAssetsSpy.mockImplementation(async (_runId, params) => {
    if (params?.asset_type === "event") {
      return { assets: baseEventAssets(), total: 1, offset: 0, limit: 200 };
    }
    if (params?.asset_type === "goal") {
      return {
        assets: [
          {
            asset_id: 202,
            asset_type: "goal",
            title: "查明真相",
            state: "candidate",
            confidence: 0.88,
            evidence_count: 1,
            subject_entity_ids: [101],
          },
        ],
        total: 1,
        offset: 0,
        limit: 100,
      };
    }
    if (params?.asset_type === "conflict") {
      return {
        assets: [
          {
            asset_id: 402,
            asset_type: "conflict",
            title: "隐瞒真相",
            state: "candidate",
            confidence: 0.7,
            evidence_count: 1,
            subject_entity_ids: [101],
          },
        ],
        total: 1,
        offset: 0,
        limit: 100,
      };
    }
    if (params?.asset_type === "question") {
      return {
        assets: [
          {
            asset_id: 403,
            asset_type: "question",
            title: "旧库藏着什么",
            state: "candidate",
            confidence: 0.72,
            evidence_count: 1,
            subject_entity_ids: [101],
          },
        ],
        total: 1,
        offset: 0,
        limit: 100,
      };
    }
    if (params?.asset_type === "setting_fact") {
      return {
        assets: [
          {
            asset_id: 401,
            asset_type: "setting_fact",
            title: "现代城市",
            state: "candidate",
            confidence: 0.75,
            evidence_count: 1,
            subject_entity_ids: [],
          },
        ],
        total: 1,
        offset: 0,
        limit: 100,
      };
    }
    return { assets: [], total: 0, offset: 0, limit: 100 };
  });
  listEvidencesSpy.mockResolvedValue({ evidences: baseEvidences() });
  getOverviewSpy.mockResolvedValue({ overview: baseOverview() });
  getEvidenceSourceSpy.mockResolvedValue({ source: baseEvidenceSource() });
}

async function setupRunReady() {
  createSnapshotSpy.mockResolvedValue({ snapshot: baseSnapshot(), reused: false });
  createRunSpy.mockResolvedValue({ run: baseRun("pending") });
  listStagesSpy.mockResolvedValue({ stages: baseStages() });
  renderDiagnostics();
  await screen.findByTestId("whole-book-diagnostics-book-select");
  await fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
  await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-snapshot"));
  await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-create-run"));
  await waitFor(() => expect(createRunSpy).toHaveBeenCalled());
}

function renderDiagnostics(initial = "/dev/whole-book-diagnostics") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/dev/whole-book-diagnostics" element={<WholeBookDiagnosticsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderAppShell(initial = "/library") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/library" element={<div>library-page</div>} />
            <Route path="/settings" element={<div>settings-page</div>} />
            <Route path="/dev/whole-book-diagnostics" element={<WholeBookDiagnosticsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WholeBookDiagnosticsPage (Wave B)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    flagState.enabled = true;
  });

  beforeEach(() => {
    flagState.enabled = true;
    createSnapshotSpy.mockReset();
    createRunSpy.mockReset();
    listStagesSpy.mockReset();
    getRunSpy.mockReset();
    generateWindowsSpy.mockReset();
    executeMinimalFixtureSpy.mockReset();
    getMinimalSummarySpy.mockReset();
    listEntitiesSpy.mockReset();
    listAssetsSpy.mockReset();
    listEvidencesSpy.mockReset();
    getOverviewSpy.mockReset();
    getEvidenceSourceSpy.mockReset();
    booksList.mockReset();
    booksChapters.mockReset();
    booksList.mockResolvedValue([
      {
        id: 1,
        title: "测试书",
        source_file_name: "book.txt",
        source_file_hash: "hash",
        created_at: "2026-07-01T00:00:00Z",
        revision_number: 1,
      },
    ]);
    booksChapters.mockResolvedValue([
      {
        id: 2,
        book_id: 1,
        chapter_index: 1,
        title: "第1章",
        display_title: "第1章",
        section_type: "chapter",
        word_count: 1200,
      },
    ]);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const href = String(input);
        if (href.includes("/api/v1/entitlements")) {
          return new Response(
            JSON.stringify({
              edition: "free",
              edition_label: "免费版",
              pro_active: false,
              features: {},
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.includes("/health")) {
          return new Response(JSON.stringify({ status: "ok" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ error_code: "HTTP_ERROR" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("shows unavailable panel when feature flag is off", async () => {
    flagState.enabled = false;
    renderDiagnostics();
    expect(await screen.findByTestId("whole-book-diagnostics-unavailable")).toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-diagnostics-page")).not.toBeInTheDocument();
  });

  it("shows banner and provider real calls as 0 when flag is on", async () => {
    renderDiagnostics();
    const banner = await screen.findByTestId("whole-book-diagnostics-banner");
    expect(banner).toHaveTextContent("当前仅验证 Snapshot、Run 和跨章窗口");
    expect(screen.getByTestId("whole-book-diagnostics-provider-real-calls")).toHaveTextContent(
      "Provider Real Calls = 0",
    );
    expect(screen.getByTestId("whole-book-diagnostics-fixture-result")).toHaveTextContent(
      "Fixture Result",
    );
  });

  it("renders snapshot reused badge when createSnapshot returns reused true", async () => {
    createSnapshotSpy.mockResolvedValue({ snapshot: baseSnapshot(), reused: true });
    renderDiagnostics();
    await screen.findByTestId("whole-book-diagnostics-book-select");
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-snapshot"));
    expect(await screen.findByTestId("whole-book-diagnostics-snapshot-reused")).toHaveTextContent(
      "已复用",
    );
  });

  it("enables and disables run controls by status", async () => {
    createSnapshotSpy.mockResolvedValue({ snapshot: baseSnapshot(), reused: false });
    createRunSpy.mockResolvedValue({ run: baseRun("pending") });
    listStagesSpy.mockResolvedValue({ stages: baseStages() });
    renderDiagnostics();
    await screen.findByTestId("whole-book-diagnostics-book-select");
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-snapshot"));
    await screen.findByTestId("whole-book-diagnostics-create-run");
    await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-run"));
    await waitFor(() => expect(createRunSpy).toHaveBeenCalled());
    const start = await screen.findByTestId("whole-book-diagnostics-run-start");
    expect(start).not.toBeDisabled();
    expect(screen.getByTestId("whole-book-diagnostics-run-pause")).toBeDisabled();
    expect(screen.getByTestId("whole-book-diagnostics-run-resume")).toBeDisabled();
  });

  it("renders coverage cards after window generation", async () => {
    createSnapshotSpy.mockResolvedValue({ snapshot: baseSnapshot(), reused: false });
    createRunSpy.mockResolvedValue({ run: baseRun("pending") });
    listStagesSpy.mockResolvedValue({ stages: baseStages() });
    generateWindowsSpy.mockResolvedValue({
      run_id: 21,
      snapshot_id: 11,
      reused: false,
      windowing_version: "whole_book_windowing_v1",
      windows: [
        {
          window_id: 31,
          run_id: 21,
          snapshot_id: 11,
          window_index: 0,
          first_global_paragraph_index: 0,
          last_global_paragraph_index: 9,
          chapter_start_index: 0,
          chapter_end_index: 0,
          paragraph_count: 10,
          character_count: 1000,
          token_estimate: 250,
          overlap_before_paragraphs: 0,
          overlap_after_paragraphs: 0,
          window_hash: "wh1",
          idempotency_key: "w0",
          status: "pending",
        },
      ],
      coverage: baseCoverage(),
      warnings: [],
    } satisfies GenerateWindowsResponse);
    renderDiagnostics();
    await screen.findByTestId("whole-book-diagnostics-book-select");
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-snapshot"));
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-create-run"));
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-generate-windows"));
    const coverage = await screen.findByTestId("whole-book-diagnostics-coverage");
    expect(coverage).toHaveTextContent("总段落");
    expect(coverage).toHaveTextContent("20");
    expect(coverage).toHaveTextContent("100%");
    expect(screen.queryByTestId("whole-book-diagnostics-coverage-alert")).not.toBeInTheDocument();
    expect(await screen.findByTestId("whole-book-diagnostics-window-table")).toBeInTheDocument();
  });

  it("shows coverage anomaly alert when coverage is incomplete", async () => {
    createSnapshotSpy.mockResolvedValue({ snapshot: baseSnapshot(), reused: false });
    createRunSpy.mockResolvedValue({ run: baseRun("pending") });
    listStagesSpy.mockResolvedValue({ stages: baseStages() });
    generateWindowsSpy.mockResolvedValue({
      run_id: 21,
      snapshot_id: 11,
      reused: false,
      windowing_version: "whole_book_windowing_v1",
      windows: [],
      coverage: {
        ...baseCoverage(),
        covered_unique_paragraphs: 18,
        uncovered_paragraphs: 2,
        coverage_ratio: 0.9,
        order_valid: false,
      },
      warnings: [],
    } satisfies GenerateWindowsResponse);
    renderDiagnostics();
    await screen.findByTestId("whole-book-diagnostics-book-select");
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    await fireEvent.click(screen.getByTestId("whole-book-diagnostics-create-snapshot"));
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-create-run"));
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-generate-windows"));
    expect(await screen.findByTestId("whole-book-diagnostics-coverage-alert")).toHaveTextContent(
      "覆盖异常",
    );
  });

  it("does not expose diagnostics in primary navigation", async () => {
    renderAppShell("/library");
    await screen.findByTestId("primary-nav");
    expect(screen.getByTestId("nav-library")).toBeInTheDocument();
    expect(screen.getByTestId("nav-settings")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-dev-whole-book-diagnostics")).not.toBeInTheDocument();
    expect(screen.queryByText("/dev/whole-book-diagnostics")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dev-nav-link-devwhole-book-diagnostics")).not.toBeInTheDocument();
  });
});

describe("WholeBookDiagnosticsPage (Wave C)", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    flagState.enabled = true;
  });

  beforeEach(() => {
    flagState.enabled = true;
    createSnapshotSpy.mockReset();
    createRunSpy.mockReset();
    listStagesSpy.mockReset();
    getRunSpy.mockReset();
    executeMinimalFixtureSpy.mockReset();
    getMinimalSummarySpy.mockReset();
    listEntitiesSpy.mockReset();
    listAssetsSpy.mockReset();
    listEvidencesSpy.mockReset();
    getOverviewSpy.mockReset();
    getEvidenceSourceSpy.mockReset();
    booksList.mockReset();
    booksChapters.mockReset();
    booksList.mockResolvedValue([
      {
        id: 1,
        title: "测试书",
        source_file_name: "book.txt",
        source_file_hash: "hash",
        created_at: "2026-07-01T00:00:00Z",
        revision_number: 1,
      },
    ]);
    booksChapters.mockResolvedValue([]);
    mockMinimalAnalysisApis();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const href = String(input);
        if (href.includes("/api/v1/entitlements")) {
          return new Response(
            JSON.stringify({
              edition: "free",
              edition_label: "免费版",
              pro_active: false,
              features: {},
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.includes("/health")) {
          return new Response(JSON.stringify({ status: "ok" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return new Response(JSON.stringify({ error_code: "HTTP_ERROR" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("shows fixture-only notice in minimal pipeline section", async () => {
    await setupRunReady();
    expect(await screen.findByTestId("whole-book-diagnostics-fixture-notice")).toHaveTextContent(
      "不调用真实模型",
    );
  });

  it("shows provider real calls remain 0 after fixture execute", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    await waitFor(() => expect(executeMinimalFixtureSpy).toHaveBeenCalled());
    expect(screen.getByTestId("whole-book-diagnostics-provider-real-calls")).toHaveTextContent(
      "Provider Real Calls = 0",
    );
  });

  it("shows pipeline progress after mock execute", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    const progress = await screen.findByTestId("whole-book-diagnostics-minimal-progress");
    expect(progress).toHaveTextContent("2 / 2");
    expect(progress).toHaveTextContent("entity_count");
    expect(progress).toHaveTextContent("provider_fixture_call_count");
    expect(progress).toHaveTextContent("2");
  });

  it("renders character table with aliases and detail", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    const table = await screen.findByTestId("whole-book-diagnostics-entity-table");
    expect(table).toHaveTextContent("林远");
    expect(table).toHaveTextContent("小林");
    await fireEvent.click(within(table).getByText("林远"));
    expect(await screen.findByTestId("whole-book-diagnostics-entity-detail")).toHaveTextContent(
      "远哥",
    );
  });

  it("renders event table ordered from fixture data", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    const table = await screen.findByTestId("whole-book-diagnostics-event-table");
    expect(table).toHaveTextContent("夜探旧库");
    expect(table).toHaveTextContent("discovery");
    expect(table).toHaveTextContent("林远");
  });

  it("shows evidence detail with quote highlight on click", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    await screen.findByTestId("whole-book-diagnostics-evidence-table");
    await fireEvent.click(screen.getByText("501"));
    const paragraph = await screen.findByTestId("whole-book-diagnostics-evidence-paragraph");
    expect(paragraph).toHaveTextContent("夜里，");
    expect(paragraph.querySelector("mark")).toHaveTextContent("林远");
    expect(await screen.findByTestId("whole-book-diagnostics-evidence-detail")).toHaveTextContent(
      "第1章",
    );
  });

  it("renders nine overview claims in fixed Chinese order", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    const list = await screen.findByTestId("whole-book-diagnostics-claim-list");
    expect(list).toHaveTextContent("小说类型及叙事特征");
    expect(list).toHaveTextContent("核心设定");
    expect(list).toHaveTextContent("主角");
    expect(list).toHaveTextContent("主角核心目标");
    expect(list).toHaveTextContent("主要矛盾");
    expect(list).toHaveTextContent("核心悬念或问题");
    expect(list).toHaveTextContent("最终解决");
    expect(list).toHaveTextContent("重要人物");
    expect(list).toHaveTextContent("关键事件");
    expect(list.querySelectorAll("li")).toHaveLength(9);
  });

  it("handles insufficient_evidence overview claim state", async () => {
    await setupRunReady();
    await fireEvent.click(await screen.findByTestId("whole-book-diagnostics-run-minimal-fixture"));
    const claim = await screen.findByTestId("whole-book-diagnostics-claim-protagonist_core_goal");
    expect(claim).toHaveAttribute("data-availability", "insufficient_evidence");
    expect(screen.getByTestId("whole-book-diagnostics-insufficient-evidence")).toHaveTextContent(
      "证据不足",
    );
  });

  it("does not expose diagnostics in primary navigation", async () => {
    renderAppShell("/library");
    await screen.findByTestId("primary-nav");
    expect(screen.queryByTestId("nav-dev-whole-book-diagnostics")).not.toBeInTheDocument();
  });

  it("does not render a real provider button", async () => {
    await setupRunReady();
    expect(screen.queryByTestId("whole-book-diagnostics-run-real-provider")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /真实.*Provider/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /真实模型/i })).not.toBeInTheDocument();
  });
});
