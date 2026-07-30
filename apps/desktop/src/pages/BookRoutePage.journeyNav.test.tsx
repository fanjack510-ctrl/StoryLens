import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BookRoutePage } from "./BookRoutePage";
import { analysisApi } from "../services/analysisApi";

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
        run: { id: 77, status: "scene_analysis_running", provider: "fake", model: "fake" },
        chapter: { id: 2, book_id: 1, title: "开端", display_title: "开端" },
        boundary_revision: { id: 3, revision_number: 1 },
        summary: { total_scene_count: 3 },
        scenes: [],
      })),
      readerJourney: vi.fn(async () => ({ status: "missing", visualization: null })),
      readerJourneyById: vi.fn(async () => ({ status: "missing", visualization: null })),
      readerJourneyProgress: vi.fn(async () => null),
      sceneBoundariesOverview: vi.fn(async () => ({
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
      })),
      sceneParagraphs: vi.fn(async () => ({ paragraphs: [] })),
      resumeSceneAnalysis: vi.fn(),
      createReaderJourney: vi.fn(),
    },
  };
});

vi.mock("../services/booksApi", () => ({
  booksApi: {
    detail: vi.fn(async () => ({ id: 1, title: "测试书" })),
    chapters: vi.fn(async () => [
      { id: 2, title: "开端", display_title: "开端", section_type: "chapter" },
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
  AnalysisResultRouteAdapter: () => <div data-testid="mock-embedded-results" />,
}));
vi.mock("../components/chapterResult/EmbeddedAnalysisResultShell", () => ({
  EmbeddedAnalysisResultShell: () => <div data-testid="embedded-analysis-result" />,
}));
vi.mock("../components/analysis/StartAnalysisDialog", () => ({
  StartAnalysisDialog: () => null,
}));
vi.mock("../components/analysis/BoundaryReviewPanel", () => ({
  BoundaryReviewPanel: () => null,
}));
vi.mock("../components/analysis/ConfirmBoundaryDivisionPanel", () => ({
  ConfirmBoundaryDivisionPanel: () => (
    <div data-testid="confirm-boundary-division">confirm</div>
  ),
}));
vi.mock("../components/analysis/SceneBoundaryReviewPanel", () => ({
  SceneBoundaryReviewPanel: () => (
    <div data-testid="shell-scene-boundary-review">boundary-review</div>
  ),
}));
vi.mock("./BookWorkspacePage", () => ({
  BookWorkspacePage: () => <div data-testid="mock-book-workspace">workspace</div>,
}));

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

describe("CHG-017 BookRoutePage journey nav", () => {
  beforeEach(() => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "scene_analysis_running",
      progress_current: 1,
      progress_total: 3,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      chapter_complete: false,
      effective_status: "scene_analysis",
      completed_scene_count: 1,
      total_scene_count: 3,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "missing",
      visualization: null,
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("hides journey tab during scene analysis even with historical journey result", async () => {
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 9,
      visualization: { scene_nodes: [], phases: [], curve_series: {} },
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("workspace-tab-journey")).not.toBeInTheDocument();
    expect(screen.getByTestId("shell-view-analysis-progress")).toHaveTextContent(
      "查看分析进度",
    );
    expect(screen.queryByText("阅读旅程尚未开始")).not.toBeInTheDocument();
  });

  it("redirects journeyRun deep link to progress during scene analysis", async () => {
    renderBook(
      "/books/1?chapter=2&analysisRun=77&view=result&tab=reader-journey&journeyRun=9",
    );
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute(
        "data-view",
        "progress",
      );
    });
    expect(screen.queryByTestId("reader-journey-blocked-unconfirmed")).not.toBeInTheDocument();
    expect(screen.queryByText("阅读旅程尚未开始")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-tab-journey")).not.toBeInTheDocument();
  });

  it("redirects journey tab to confirmation while awaiting scenes", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "awaiting_boundary_review",
      progress_current: 0,
      progress_total: 1,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: null,
      chapter_complete: false,
      effective_status: "awaiting_scene_boundary_confirmation",
      completed_scene_count: 0,
      total_scene_count: 3,
    } as any);
    vi.mocked(analysisApi.sceneBoundariesOverview).mockResolvedValue({
      chapter_id: 2,
      chapter_text_hash: "h",
      confirmed_revision: null,
      draft_revision: {
        revision_id: 2,
        revision_number: 1,
        status: "draft",
        source: "model",
        scenes: [{ ordinal: 1 }, { ordinal: 2 }, { ordinal: 3 }],
      },
      model_revision: null,
      awaiting_confirmation: true,
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77&view=result&tab=reader-journey");
    await waitFor(() => {
      expect(screen.getAllByTestId("shell-scene-boundary-review").length).toBeGreaterThan(0);
    });
    expect(screen.queryByText("阅读旅程尚未开始")).not.toBeInTheDocument();
    expect(screen.queryByTestId("workspace-tab-journey")).not.toBeInTheDocument();
  });

  it("shows journey tab once journey_starting", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
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
      completed_at: null,
      chapter_complete: false,
      effective_status: "partial_complete",
      journey_status: "starting",
      completed_scene_count: 3,
      total_scene_count: 3,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "starting",
      journey_run_id: 12,
      visualization: null,
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toBeInTheDocument();
    });
    expect(screen.getByTestId("shell-view-analysis-progress")).toHaveTextContent(
      "查看分析进度",
    );
    expect(screen.getByTestId("workspace-tab-journey")).toHaveAttribute(
      "data-nav-primary",
      "false",
    );
  });

  it("journey_succeeded on progress: 阅读旅程 primary, progress secondary, open journey CTA", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
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
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 12,
      visualization: { scenes: [] },
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 12,
      completed_scene_count: 3,
      total_scene_count: 3,
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77&view=progress&journeyRun=12");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute(
        "data-journey-nav-primary",
        "true",
      );
    });
    expect(screen.getByTestId("workspace-tab-journey")).toHaveAttribute(
      "data-nav-primary",
      "true",
    );
    expect(screen.getByTestId("shell-view-analysis-progress-secondary")).toHaveTextContent(
      "查看分析进度",
    );
    expect(screen.queryByTestId("shell-view-analysis-progress")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-success-title")).toHaveTextContent(
        "阅读旅程已生成",
      );
    });
    expect(screen.getByTestId("chapter-analysis-open-journey")).toHaveTextContent(
      "查看阅读旅程",
    );
    expect(screen.getByTestId("chapter-analysis-open-journey").className).toContain("primary");
    const toolbarPrimaries = screen
      .getByTestId("book-shell-toolbar")
      .querySelectorAll("button.primary");
    expect(toolbarPrimaries.length).toBe(1);
    expect(toolbarPrimaries[0]).toHaveAttribute("data-testid", "workspace-tab-journey");
  });

  it("journey_succeeded on reading journey: journey primary, progress secondary only", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
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
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 12,
      visualization: { scenes: [] },
    } as any);
    vi.mocked(analysisApi.readerJourneyById).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 12,
      visualization: { scenes: [] },
    } as any);
    vi.mocked(analysisApi.readerJourneyProgress).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 12,
      completed_scene_count: 3,
      total_scene_count: 3,
    } as any);

    renderBook(
      "/books/1?chapter=2&analysisRun=77&view=result&tab=reader-journey&journeyRun=12",
    );
    await waitFor(() => {
      expect(screen.getByTestId("workspace-tab-journey")).toHaveAttribute(
        "data-nav-primary",
        "true",
      );
    });
    expect(screen.getByTestId("shell-view-analysis-progress-secondary")).toBeInTheDocument();
    expect(screen.queryByTestId("shell-view-analysis-progress")).not.toBeInTheDocument();
    const toolbarPrimaries = screen
      .getByTestId("book-shell-toolbar")
      .querySelectorAll("button.primary");
    expect(toolbarPrimaries.length).toBe(1);
  });
});
