import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BookRoutePage } from "./BookRoutePage";
import { analysisApi } from "../services/analysisApi";
import { booksApi } from "../services/booksApi";

vi.mock("../services/analysisApi", async () => {
  const actual = await vi.importActual<typeof import("../services/analysisApi")>(
    "../services/analysisApi",
  );
  return {
    analysisApi: {
      ...actual.analysisApi,
      runs: vi.fn(async () => []),
      run: vi.fn(),
      results: vi.fn(async () => ({
        run: { id: 5, status: "succeeded", provider: "aliyun_qwen_plus", model: "qwen3.7-plus" },
        chapter: { id: 2, book_id: 1, title: "开端", display_title: "第1章 开端" },
        boundary_revision: { id: 1, revision_number: 1 },
        summary: { total_scene_count: 13 },
        scenes: [],
      })),
      readerJourney: vi.fn(async () => null),
      readerJourneyPreflight: vi.fn(),
      createReaderJourney: vi.fn(),
      resumeReaderJourney: vi.fn(),
      readerJourneyProgress: vi.fn(),
      resumeSceneAnalysis: vi.fn(),
    },
  };
});


vi.mock("../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 5,
      status: "succeeded",
      user_status: "paused_recoverable",
      recoverable: true,
      blockers: [
        {
          code: "AWAITING_READER_JOURNEY",
          reason: "awaiting_reader_journey",
          user_message: "阅读旅程尚未生成",
        },
      ],
      warnings: [],
      checks: [
        {
          id: "scene_artifacts",
          label: "req",
          status: "pass",
          user_label: "Scene分析已完成",
        },
      ],
      recommended_actions: [],
      resume_stage: "reader_journey",
      will_reuse_artifacts: [],
      will_create_entities: [],
      estimated_requests: 0,
      estimated_tokens: 0,
      estimated_cost: 0,
      currency: "CNY",
      recovery_attempts: 0,
      details: {},
    })),
    recover: vi.fn(),
  },
}));

vi.mock("../services/booksApi", () => ({
  booksApi: {
    detail: vi.fn(async () => ({ id: 1, title: "UAT Book" })),
    chapters: vi.fn(async () => [
      { id: 2, title: "开端", display_title: "第1章 开端", section_type: "chapter" },
    ]),
  },
}));

vi.mock("../services/settingsApi", () => ({
  settingsApi: {
    cloudUsage: vi.fn(async () => ({
      remaining_requests: 50,
      remaining_tokens: 900000,
      remaining_estimated_cost: 20,
    })),
  },
}));

vi.mock("../components/chapterResult/AnalysisResultRouteAdapter", () => ({
  AnalysisResultRouteAdapter: ({ runId }: { runId: number }) => (
    <div data-testid="mock-embedded-results">embedded-run:{runId}</div>
  ),
}));

vi.mock("../components/chapterResult/EmbeddedAnalysisResultShell", () => ({
  EmbeddedAnalysisResultShell: ({ runId }: { runId: number }) => (
    <div data-testid="embedded-analysis-result" data-run-id={runId}>
      <div data-testid="mock-embedded-results">embedded-run:{runId}</div>
    </div>
  ),
}));

vi.mock("../components/analysis/StartAnalysisDialog", () => ({
  StartAnalysisDialog: () => null,
}));

vi.mock("../components/analysis/BoundaryReviewPanel", () => ({
  BoundaryReviewPanel: () => null,
}));
vi.mock("../components/analysis/ConfirmBoundaryDivisionPanel", () => ({
  ConfirmBoundaryDivisionPanel: () => (
    <div data-testid="confirm-boundary-division">confirm-boundary-stub</div>
  ),
}));

vi.mock("./BookWorkspacePage", () => ({
  BookWorkspacePage: () => <div data-testid="mock-book-workspace">workspace</div>,
}));


function succeededRun(extra: Record<string, unknown> = {}) {
  return {
    id: 5,
    subject_id: "2",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status: "succeeded",
    current_stage: "completed",
    progress_current: 13,
    progress_total: 13,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    chapter_complete: false,
    effective_status: "partial_complete",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    completed_scene_count: 13,
    total_scene_count: 13,
    ...extra,
  } as any;
}

function renderBook(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookRoutePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BookRoutePage reader journey resume entry", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(analysisApi.run).mockResolvedValue(succeededRun());
    vi.mocked(analysisApi.readerJourney).mockResolvedValue(null);
    vi.mocked(analysisApi.readerJourneyPreflight).mockResolvedValue({
      analysis_run_id: 5,
      total_scenes: 13,
      remaining_scenes: 13,
      scene_batch_count: 3,
      expected_requests: 14,
      worst_case_requests: 16,
      estimated_tokens: 1000,
      worst_case_tokens: 2000,
      estimated_cost: 0.5,
      worst_case_cost: 0.8,
      within_budget: true,
      exceeded_dimensions: [],
      provider_state_version: "v1",
      provider_name: "aliyun_qwen_plus",
      eligible: true,
      blockers: [],
      requires_cloud_consent: true,
      currency: "CNY",
    });
    vi.mocked(analysisApi.createReaderJourney).mockResolvedValue({
      journey_run_id: 42,
      status: "queued",
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("restores workspace from stale view=result while journey is pending", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=result");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "progress");
    });
    expect(screen.getByTestId("workspace-view-switcher")).toBeInTheDocument();
    // CHG-011/017: ordinary nav has reading + journey (not 场景分析 tab).
    expect(screen.queryByTestId("workspace-tab-analysis")).not.toBeInTheDocument();
    expect(screen.getByTestId("workspace-tab-journey")).toHaveTextContent("阅读旅程");
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(screen.queryByText("分析全部完成")).not.toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("keeps journey pending on progress without auto-create (no scene analysis tab)", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
    });
    expect(screen.queryByTestId("workspace-tab-analysis")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-analysis-run", "5");
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("keeps AnalysisRun #5 on journey tab without auto-create", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("workspace-tab-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-analysis-run", "5");
    });
    // CHG-018: awaiting / starting journey must not mount stale paused recovery card.
    expect(screen.queryByTestId("unified-recovery-card")).not.toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
    expect(booksApi.chapters).toHaveBeenCalled();
  });

  it("shows journey progress card while processing and keeps run id", async () => {
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "scene_profiles_running",
      formula_version: "v1",
      phases: [],
      scene_profiles: [],
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "scene_profiles_running",
      total_scene_count: 13,
      completed_scene_count: 4,
      remaining_scene_count: 9,
      completed_scene_ids: [],
      remaining_scene_ids: [],
      phase_count: 0,
      has_chapter_summary: false,
      retryable: true,
    });
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
      expect(screen.getByTestId("chapter-analysis-progress")).toHaveAttribute(
        "data-ui-state",
        "reader_journey_processing",
      );
    });
    fireEvent.click(screen.getByTestId("workspace-tab-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-progress-scenes")).toHaveTextContent("4 / 13");
    });
    expect(screen.getByTestId("reader-journey-progress-card")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-analysis-run", "5");
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
    expect(analysisApi.readerJourneyProgress).toHaveBeenCalledWith(42);
  });

  it("shows journey interrupted StateView for retryable journey failure", async () => {
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "failed",
      user_error_message: "阅读旅程生成失败",
      retryable: true,
      formula_version: "v1",
      phases: [],
      scene_profiles: [],
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "failed",
      total_scene_count: 13,
      completed_scene_count: 2,
      remaining_scene_count: 11,
      completed_scene_ids: [],
      remaining_scene_ids: [],
      phase_count: 0,
      has_chapter_summary: false,
      retryable: true,
      user_error_message: "阅读旅程生成失败",
    });
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("workspace-tab-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("journey-interrupted")).toBeInTheDocument();
    });
    expect(screen.getByTestId("journey-interrupted")).toHaveTextContent("阅读旅程已中断");
    expect(screen.getByTestId("journey-interrupted-task-details")).toHaveTextContent("查看详情");
    expect(screen.queryByTestId("journey-failed")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mock-embedded-results")).not.toBeInTheDocument();
    expect(screen.queryByTestId("reader-journey-progress-card")).not.toBeInTheDocument();
  });

  it("shows terminal journey failed StateView when failure is not retryable", async () => {
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "failed",
      user_error_message: "阅读旅程生成失败",
      retryable: false,
      formula_version: "v1",
      phases: [],
      scene_profiles: [],
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "failed",
      total_scene_count: 13,
      completed_scene_count: 2,
      remaining_scene_count: 11,
      completed_scene_ids: [],
      remaining_scene_ids: [],
      phase_count: 0,
      has_chapter_summary: false,
      retryable: false,
      user_error_message: "阅读旅程生成失败",
    });
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("workspace-tab-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("journey-failed")).toBeInTheDocument();
    });
    expect(screen.getByTestId("journey-failed")).toHaveTextContent("阅读旅程生成失败");
    expect(screen.getByTestId("journey-failed-retry")).toHaveTextContent("重新生成");
    expect(screen.getByTestId("journey-failed-task-details")).toHaveTextContent("查看任务详情");
    expect(screen.queryByTestId("reader-journey-progress-card")).not.toBeInTheDocument();
  });

  it("does not show failure banner when parent says journey is still running", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue(
      succeededRun({
        effective_status: "journey_running",
        journey_status: "scene_profiles_running",
        journey_run_id: 42,
        journey_completed_scene_count: 4,
        journey_total_scene_count: 13,
        scene_pipeline_complete: true,
      }),
    );
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "failed",
      retryable: false,
      formula_version: "v1",
      phases: [],
      scene_profiles: [],
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      journey_run_id: 42,
      analysis_run_id: 5,
      status: "scene_profiles_running",
      total_scene_count: 13,
      completed_scene_count: 4,
      remaining_scene_count: 9,
      completed_scene_ids: [],
      remaining_scene_ids: [],
      phase_count: 0,
      has_chapter_summary: false,
      retryable: true,
    });
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeEnabled();
    });
    fireEvent.click(screen.getByTestId("workspace-tab-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("reader-journey-progress-card")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("journey-failed")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-interrupted")).not.toBeInTheDocument();
  });

  it("reading banner does not claim full completion without journey", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-scene-complete-banner")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("chapter-analysis-complete-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-scene-complete-banner").textContent).toMatch(
      /正在衔接阅读旅程|阅读旅程/,
    );
  });
});
