import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BookRoutePage } from "./BookRoutePage";
import { analysisApi } from "../services/analysisApi";

vi.mock("../services/analysisApi", () => ({
  analysisApi: {
    runs: vi.fn(),
    run: vi.fn(),
    readerJourney: vi.fn(async () => ({ status: "missing" })),
    resumeSceneAnalysis: vi.fn(),
    sceneAnalysisResumePreflight: vi.fn(),
  },
}));


vi.mock("../services/analysisRecoveryApi", () => ({
  analysisRecoveryApi: {
    recoveryPlan: vi.fn(async () => ({
      run_id: 5,
      status: "boundary_confirmed_budget_blocked",
      user_status: "paused_recoverable",
      recoverable: true,
      blockers: [
        {
          code: "REQUEST_BUDGET_INSUFFICIENT",
          reason: "request_budget_insufficient",
          user_message: "今日云端请求额度不足",
        },
      ],
      warnings: [],
      checks: [
        {
          id: "request_budget",
          label: "req",
          status: "fail",
          user_label: "请求额度不足",
        },
      ],
      recommended_actions: [],
      resume_stage: "scene_analysis",
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

vi.mock("../services/settingsApi", () => ({
  settingsApi: {
    cloudUsage: vi.fn(async () => ({
      request_count: 17,
      remaining_requests: 13,
      total_tokens: 1000,
      estimated_cost: 0.1,
      remaining_tokens: 164405,
      remaining_estimated_cost: 19.87,
    })),
    cloudBudget: vi.fn(async () => ({
      cloud_daily_request_limit: 50,
      cloud_daily_estimated_cost_limit: 20,
      currency: "CNY",
    })),
    saveCloudBudget: vi.fn(),
  },
}));

vi.mock("../pages/BookWorkspacePage", () => ({
  BookWorkspacePage: () => <div data-testid="workspace-stub">workspace</div>,
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


vi.stubGlobal(
  "fetch",
  vi.fn(async (url: string) => {
    const href = String(url);
    if (href.includes("/chapters")) {
      return new Response(
        JSON.stringify([
          {
            id: 2,
            section_type: "chapter",
            title: "渐临倒闭的恐怖屋",
            display_title: "第1章 渐临倒闭的恐怖屋",
          },
          {
            id: 3,
            section_type: "chapter",
            title: "第二章",
            display_title: "第2章",
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (href.match(/\/books\/\d+$/)) {
      return new Response(
        JSON.stringify({ id: 1, title: "测试书", created_at: "2026-01-01T00:00:00Z" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }),
);

const run5 = {
  id: 5,
  subject_id: "2",
  provider: "aliyun_qwen_plus",
  model: "qwen",
  status: "boundary_confirmed_budget_blocked",
  progress_current: 0,
  progress_total: 13,
  execution_mode: "cloud",
  cloud_consent: true,
  sends_content_to_cloud: true,
  retryable: true,
  created_at: "2026-07-19T12:00:00Z",
  reusable_checkpoint_count: 0,
  conflicted_checkpoint_count: 0,
  checkpoint_total_count: 0,
  checkpoint_available: false,
  error_code: "INSUFFICIENT_BUDGET_RESERVATION",
  failed_stage: "scene_analysis_budget",
  current_stage: "scene_analysis",
  total_scene_count: 13,
  completed_scene_count: 0,
  scene_analysis_resume_available: true,
  budget_required: { requests: 26, tokens: 1000, estimated_cost: 0.3 },
  budget_remaining: { requests: 13, tokens: 164405, estimated_cost: 19.87 },
  exceeded_dimensions: ["requests"],
};

const olderFailed = {
  ...run5,
  id: 4,
  status: "failed",
  error_code: "PROVIDER_ERROR",
  failed_stage: "scene_analysis",
  created_at: "2026-07-18T12:00:00Z",
  scene_analysis_resume_available: false,
};

function SearchProbe() {
  const [params] = useSearchParams();
  return (
    <div
      data-testid="search-probe"
      data-chapter={params.get("chapter") || ""}
      data-view={params.get("view") || ""}
      data-analysis-run={params.get("analysisRun") || ""}
      data-tab={params.get("tab") || ""}
    />
  );
}

function renderBook(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/books/:bookId"
            element={
              <>
                <BookRoutePage />
                <SearchProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("BookRoutePage active run auto discovery", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(analysisApi.runs).mockResolvedValue([olderFailed, run5] as any);
    vi.mocked(analysisApi.run).mockImplementation(async (id: number) => {
      if (id === 5) return run5 as any;
      if (id === 4) return olderFailed as any;
      throw new Error(`unexpected run ${id}`);
    });
    // Prior cases may override this with a succeeded visualization; budget-pause
    // must not inherit that or journeyPageActive will suppress the recovery card.
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({ status: "missing" } as any);
  });

  afterEach(cleanup);

  it("library open replaces into first chapter reading without analysisRun", async () => {
    renderBook("/books/1");
    await waitFor(() => {
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "2");
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-view", "reading");
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-tab", "");
    expect(screen.queryByTestId("book-home-catalog")).not.toBeInTheDocument();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-book-home", "false");
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    expect(analysisApi.run).not.toHaveBeenCalled();
  });

  it("does not auto-bind historical complete runs on chapter reading", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      {
        ...run5,
        id: 5,
        subject_id: "2",
        status: "succeeded",
        chapter_complete: true,
        completed_scene_count: 13,
        total_scene_count: 13,
      },
    ] as any);
    renderBook("/books/1?chapter=2&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-stub")).toBeInTheDocument();
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    expect(analysisApi.run).not.toHaveBeenCalled();
  });

  it("does not auto-bind in-flight runs into the URL", async () => {
    renderBook("/books/1?chapter=2");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-stub")).toBeInTheDocument();
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.queryByTestId("chapter-analysis-run-id")).not.toBeInTheDocument();
    expect(analysisApi.run).not.toHaveBeenCalled();
  });

  it("does not auto-open journey tab when a complete chapter run exists", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      {
        ...run5,
        id: 5,
        subject_id: "2",
        status: "succeeded",
        chapter_complete: true,
        completed_scene_count: 13,
        total_scene_count: 13,
      },
    ] as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      ...run5,
      id: 5,
      subject_id: "2",
      status: "succeeded",
      chapter_complete: true,
      completed_scene_count: 13,
      total_scene_count: 13,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 7,
      visualization: {
        scene_nodes: [{ scene_ordinal: 1, scores: { reading_momentum: 1 }, engagement: {} }],
        phases: [{ ordinal: 1 }],
        curve_series: { engagement: [{ scene_ordinal: 1, value: 1 }] },
      },
    } as any);
    renderBook("/books/1?chapter=2&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    });
    expect(screen.queryByTestId("workspace-journey-pane")).not.toBeInTheDocument();
  });

  it("keeps explicit deep link analysisRun=5", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-run-id")).toHaveTextContent("#5");
    });
    expect(analysisApi.runs).toHaveBeenCalled();
  });

  it("keeps explicit chapter=3 deep link without binding another chapter run", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      olderFailed,
      run5,
      {
        ...run5,
        id: 9,
        subject_id: "3",
        status: "scene_analysis_running",
        completed_scene_count: 1,
        error_code: undefined,
        failed_stage: undefined,
        exceeded_dimensions: [],
      },
    ] as any);
    renderBook("/books/1?chapter=3&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "3");
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.queryByTestId("chapter-analysis-run-id")).not.toBeInTheDocument();
  });

  it("shows budget pause modal once for explicit analysisRun deep link", async () => {
    renderBook("/books/1?chapter=2&analysisRun=5&view=progress");
    await waitFor(() => expect(screen.getByTestId("budget-pause-modal")).toBeInTheDocument());
    // Inline recovery card must already be present beside the one-shot modal.
    expect(await screen.findByTestId("unified-recovery-card")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toHaveAttribute(
      "data-ui-state",
      "awaiting_budget_adjustment",
    );
    fireEvent.click(
      within(screen.getByTestId("budget-pause-modal")).getByTestId("unified-recovery-later"),
    );
    await waitFor(() =>
      expect(screen.queryByTestId("budget-pause-modal")).not.toBeInTheDocument(),
    );
    // Dismissing the modal must not collapse the progress rail recovery surface.
    expect(screen.getByTestId("unified-recovery-card")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    // Simulate poll refresh of same run id — modal must stay closed.
    await waitFor(() => expect(analysisApi.run).toHaveBeenCalled());
    expect(screen.queryByTestId("budget-pause-modal")).not.toBeInTheDocument();
  });
});
