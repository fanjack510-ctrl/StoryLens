import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WholeBookDiagnosticsPage } from "./WholeBookDiagnosticsPage";
import { AppShell } from "../components/layout/AppShell";
import * as foundationApiMod from "../services/wholeBookFoundationApi";
import type {
  BookSnapshotMetadata,
  GenerateWindowsResponse,
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
const generateWindowsSpy = vi.spyOn(foundationApiMod.wholeBookFoundationApi, "generateWindows");

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
    generateWindowsSpy.mockReset();
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

  it("shows banner and provider calls as 0 when flag is on", async () => {
    renderDiagnostics();
    const banner = await screen.findByTestId("whole-book-diagnostics-banner");
    expect(banner).toHaveTextContent("当前仅验证 Snapshot、Run 和跨章窗口");
    expect(screen.getByTestId("whole-book-diagnostics-provider-calls")).toHaveTextContent("0");
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
