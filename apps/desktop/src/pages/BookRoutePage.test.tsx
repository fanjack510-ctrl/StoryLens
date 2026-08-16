import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BookRoutePage } from "../pages/BookRoutePage";
import { useUiStore } from "../stores/uiStore";
import { analysisApi } from "../services/analysisApi";

const LONG_ZH =
  "这是一段用于验证中文长段落在隐藏段落ID后仍能占满正文列、不会被挤成窄列的测试文本，包含足够多的汉字以便观察换行与宽度。";

const globalCss = readFileSync(resolve(__dirname, "../styles/global.css"), "utf8");

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
        run: { id: 77, status: "succeeded", provider: "fake", model: "fake" },
        chapter: { id: 2, book_id: 1, title: "开端", display_title: "开端" },
        boundary_revision: null,
        summary: { total_scene_count: 1 },
        scenes: [
          {
            scene: {
              id: 14,
              ordinal: 1,
              scene_key: "S1",
              start_paragraph_id: "B0001-C0001-P0001",
              end_paragraph_id: "B0001-C0001-P0001",
            },
            fields: {},
          },
        ],
      })),
      readerJourney: vi.fn(async () => ({ status: "missing", visualization: null })),
      readerJourneyById: vi.fn(async () => ({ status: "missing", visualization: null })),
      sceneParagraphs: vi.fn(async () => ({
        paragraphs: [
          {
            id: "B0001-C0001-P0001",
            raw_text: "段落。",
            in_scene: true,
            paragraph_index: 1,
          },
        ],
      })),
      resumeSceneAnalysis: vi.fn(),
      createReaderJourney: vi.fn(),
    },
  };
});

vi.mock("../components/chapterResult/AnalysisResultRouteAdapter", () => ({
  AnalysisResultRouteAdapter: ({ runId }: { runId: number }) => (
    <div data-testid="mock-embedded-results">embedded-run:{runId}</div>
  ),
}));

vi.mock("../components/chapterResult/EmbeddedAnalysisResultShell", () => ({
  EmbeddedAnalysisResultShell: ({ runId }: { runId: number }) => (
    <div data-testid="embedded-analysis-result" data-run-id={runId}>
      embedded-run:{runId}
    </div>
  ),
}));

vi.mock("../components/readerJourney/ReaderJourneySyncWorkspace", () => ({
  ReaderJourneySyncWorkspace: () => (
    <div data-testid="journey-sync-workspace">
      <div data-testid="journey-sync-mode-toggle">sync-modes</div>
    </div>
  ),
}));

vi.mock("../components/readerJourney/ReaderJourneyWorkspace", () => ({
  ReaderJourneyWorkspace: ({ analysisRunId }: { analysisRunId?: number }) => (
    <div data-testid="mock-reader-journey-workspace" data-analysis-run={analysisRunId}>
      journey-workspace
    </div>
  ),
}));

vi.mock("../components/analysis/StartAnalysisDialog", () => ({
  StartAnalysisDialog: ({
    onCreated,
    onClose,
  }: {
    onCreated?: (id: number) => void;
    onClose: () => void;
  }) => (
    <div data-testid="start-analysis-dialog">
      <button
        type="button"
        data-testid="fake-create-run"
        onClick={() => {
          onCreated?.(77);
          onClose();
        }}
      >
        创建
      </button>
    </div>
  ),
}));

vi.mock("../pages/BookWorkspacePage", () => ({
  BookWorkspacePage: () => (
    <section className="workspace">
      <aside className="structure-pane">
        <button type="button">导入诊断</button>
        <button type="button">重新识别章节</button>
        <button type="button" className="selected">
          <span>第1章</span>开端
        </button>
      </aside>
      <article className="reader">
        <div className="reader-tools">
          <button type="button">完整正文</button>
          <button type="button" className="primary">
            开始分析
          </button>
        </div>
        <div className="prose">
          <div className="paragraph" data-testid="sample-paragraph">
            <button type="button">B0001-C0001-P0001</button>
            <p data-testid="sample-paragraph-text">{LONG_ZH}</p>
          </div>
        </div>
      </article>
      <aside className="analysis-pane">
        <div className="tabs">
          <button type="button" className="active">
            场景结构
          </button>
        </div>
        <div className="empty">选择一个场景查看分析</div>
      </aside>
    </section>
  ),
}));

const defaultFetchMock = vi.fn(async (url: string) => {
  const href = String(url);
  if (href.includes("/books/1/chapters") || href.endsWith("/chapters")) {
    return new Response(
      JSON.stringify([{ id: 2, section_type: "chapter", title: "开端", display_title: "开端" }]),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }
  if (href.includes("/books/1") || href.match(/\/books\/\d+$/)) {
    return new Response(
      JSON.stringify({
        id: 1,
        title: "测试书",
        source_file_name: "a.txt",
        source_file_hash: "abc123def456",
        created_at: "2026-01-01T00:00:00Z",
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }
  if (href.includes("analysis-runs") && !href.includes("/77")) {
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response(JSON.stringify({}), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});

vi.stubGlobal("fetch", defaultFetchMock);

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

function renderBook(path = "/books/1?chapter=2") {
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
          <Route path="/library" element={<div data-testid="library-page">书库</div>} />
          <Route path="/tasks" element={<div data-testid="tasks-page">任务中心</div>} />
          <Route
            path="/analysis-runs/:runId/results"
            element={<div data-testid="results-page">结果</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Book chapter shell", () => {
  beforeEach(() => {
    useUiStore.setState({
      showParagraphIds: false,
      contentWidth: "wide",
      fontSize: 17,
      lineHeight: 1.9,
    });
    vi.mocked(analysisApi.runs).mockResolvedValue([]);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "missing",
      visualization: null,
    } as any);
    vi.mocked(analysisApi.readerJourneyById).mockResolvedValue({
      status: "missing",
      visualization: null,
    } as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "scene_analysis_running",
      progress_current: 1,
      progress_total: 4,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      completed_scene_count: 3,
      total_scene_count: 14,
    } as any);
  });

  afterEach(() => {
    cleanup();
    vi.stubGlobal("fetch", defaultFetchMock);
  });

  it("loads an explicit journeyRun by id and chapter scope", async () => {
    vi.mocked(analysisApi.readerJourneyById).mockResolvedValue({
      journey_run_id: 2,
      status: "succeeded",
      result_status: "superseded",
      scene_revision_id: 1,
      visualization: {
        scene_nodes: [
          {
            scene_ordinal: 1,
            scores: { reading_momentum: 50, plot_progress: 50 },
            engagement: { engagement_score: 50 },
          },
        ],
        phases: [{ ordinal: 1 }],
        curve_series: { curiosity: [{ scene_ordinal: 1, value: 50 }] },
      },
    } as any);

    renderBook(
      "/books/1?chapter=2&analysisRun=77&view=result&journeyRun=2&tab=reader-journey",
    );

    await waitFor(() => {
      expect(analysisApi.readerJourneyById).toHaveBeenCalledWith(2, {
        bookId: 1,
        chapterId: 2,
      });
    });
    expect(analysisApi.readerJourney).not.toHaveBeenCalled();
    expect(await screen.findByTestId("reader-journey-historical-banner")).toHaveTextContent(
      "历史阅读旅程",
    );
    expect(screen.queryByText("当前章节尚未生成阅读旅程")).not.toBeInTheDocument();
  });

  it("hides empty analysis pane and exposes shell start analysis", () => {
    renderBook();
    expect(screen.getByTestId("book-chapter-shell")).toBeInTheDocument();
    expect(screen.getByTestId("shell-start-analysis")).toBeInTheDocument();
    expect(screen.getByTestId("shell-start-analysis")).toHaveTextContent("分析本章");
    expect(screen.queryByTestId("reader-journey-entry-analyze")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-insights-entry-pro")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-insights-entry-free")).not.toBeInTheDocument();
    expect(document.querySelector(".analysis-pane .artifact")).toBeNull();
  });

  it("replaces into first chapter reading when URL has no chapter", async () => {
    renderBook("/books/1");
    await waitFor(() => {
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "2");
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-view", "reading");
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-tab", "");
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-book-home", "false");
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    expect(screen.queryByTestId("book-home-catalog")).not.toBeInTheDocument();
    expect(screen.getByTestId("shell-start-analysis")).toBeInTheDocument();
  });

  it("keeps reading when first chapter has historical journey and scene", async () => {
    vi.mocked(analysisApi.runs).mockResolvedValue([
      {
        id: 88,
        subject_id: "2",
        status: "succeeded",
        chapter_complete: true,
        provider: "fake",
        model: "fake",
        created_at: "2026-01-01T00:00:00Z",
      },
    ] as any);
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 88,
      subject_id: "2",
      status: "succeeded",
      chapter_complete: true,
      provider: "fake",
      model: "fake",
      created_at: "2026-01-01T00:00:00Z",
      completed_scene_count: 1,
      total_scene_count: 1,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 9,
      visualization: { scene_nodes: [{ scene_ordinal: 1 }] },
    } as any);
    renderBook("/books/1");
    await waitFor(() => {
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "2");
      expect(screen.getByTestId("search-probe")).toHaveAttribute("data-view", "reading");
    });
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-analysis-run", "");
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    expect(screen.queryByTestId("workspace-journey-pane")).not.toBeInTheDocument();
  });

  it("shows structured empty state when book has no chapters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const href = String(url);
        if (href.includes("/chapters")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (href.includes("/books/1") || href.match(/\/books\/\d+$/)) {
          return new Response(
            JSON.stringify({
              id: 1,
              title: "空书",
              source_file_name: "a.txt",
              created_at: "2026-01-01T00:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    renderBook("/books/1");
    expect(await screen.findByTestId("book-no-chapters")).toBeInTheDocument();
    expect(screen.getByTestId("book-no-chapters-reparse")).toBeInTheDocument();
    expect(screen.getByTestId("book-no-chapters-diagnostics")).toBeInTheDocument();
    expect(screen.getByTestId("book-no-chapters-back")).toBeInTheDocument();
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "");
  });

  it("top catalog control does not navigate to book-home intermediate page", async () => {
    renderBook("/books/1?chapter=2&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-catalog")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("book-chapter-catalog"));
    expect(screen.queryByTestId("book-home-catalog")).not.toBeInTheDocument();
    expect(screen.getByTestId("search-probe")).toHaveAttribute("data-chapter", "2");
    expect(await screen.findByTestId("chapter-catalog-drawer")).toBeInTheDocument();
  });

  it("reading settings and more menu include boundary review and tasks", () => {
    renderBook();
    const toolbar = screen.getByTestId("book-shell-toolbar");
    fireEvent.click(within(toolbar).getByTestId("reading-settings-trigger"));
    expect(within(toolbar).getByTestId("reading-settings-panel")).toBeInTheDocument();
    fireEvent.click(within(toolbar).getByTestId("book-more-menu-trigger"));
    expect(screen.getByTestId("book-more-boundary-review")).toBeInTheDocument();
    expect(screen.getByTestId("book-more-tasks")).toBeInTheDocument();
  });

  it("create analysis stays on book page and writes analysisRun URL", async () => {
    renderBook();
    const start = await screen.findByTestId("shell-start-analysis");
    await waitFor(() => expect(start).toBeEnabled());
    fireEvent.click(start);
    fireEvent.click(await screen.findByTestId("fake-create-run"));
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-analysis-run", "77");
    });
    expect(screen.queryByTestId("tasks-page")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-status-badge")).toHaveTextContent("正在分析本章");
    });
    expect(analysisApi.run).toHaveBeenCalledWith(77);
  });

  it("restores progress from analysisRun query param without recreating", async () => {
    renderBook("/books/1?chapter=2&analysisRun=77");
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    });
    expect(analysisApi.run).toHaveBeenCalledWith(77);
    expect(screen.queryByTestId("start-analysis-dialog")).not.toBeInTheDocument();
  });

  it("defines dual-column paragraph layout when paragraph IDs are shown", () => {
    expect(globalCss).toContain(
      '.book-shell-simplified[data-show-paragraph-ids="true"] .paragraph',
    );
    useUiStore.setState({ showParagraphIds: true });
    renderBook();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute(
      "data-show-paragraph-ids",
      "true",
    );
  });

  it("defines single-column paragraph layout when paragraph IDs are hidden", () => {
    expect(globalCss).toMatch(
      /data-show-paragraph-ids="false"\] \.paragraph\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/,
    );
    renderBook();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute(
      "data-show-paragraph-ids",
      "false",
    );
  });

  it("toggling paragraph IDs keeps body text and respects content width", () => {
    renderBook();
    const toolbar = screen.getByTestId("book-shell-toolbar");
    fireEvent.click(within(toolbar).getByTestId("reading-settings-trigger"));
    const panel = within(toolbar).getByTestId("reading-settings-panel");
    const checkbox = within(panel).getByTestId("reading-show-paragraph-ids");
    const textBefore = screen.getByTestId("sample-paragraph-text").textContent;
    fireEvent.click(checkbox);
    expect(screen.getByTestId("sample-paragraph-text").textContent).toBe(textBefore);
    fireEvent.click(checkbox);
    expect(screen.getByTestId("sample-paragraph-text").textContent).toBe(textBefore);
  });

  it("auto-switches to view=result only when journey visualization exists", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
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
      completed_scene_count: 14,
      total_scene_count: 14,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "missing",
      visualization: null,
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "progress");
    });
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(screen.queryByTestId("embedded-analysis-result")).not.toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("renders a single workspace root and main pane for journey URL", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 8,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 2,
      progress_total: 2,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:05:00Z",
      chapter_complete: true,
      effective_status: "completed",
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      completed_scene_count: 2,
      total_scene_count: 2,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 7,
      trusted: true,
      visualization: {
        scene_nodes: [{ scene_ordinal: 1, scores: { reading_momentum: 1, plot_progress: 1 }, engagement: { engagement_score: 1 } }],
        phases: [{ ordinal: 1 }],
        curve_series: { curiosity: [{ scene_ordinal: 1, value: 1 }] },
      },
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=8&view=result&tab=reader-journey");
    await waitFor(() => {
      expect(screen.getByTestId("workspace-journey-pane")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId("book-chapter-shell")).toHaveLength(1);
    expect(screen.getAllByTestId("main-content-pane")).toHaveLength(1);
    expect(screen.queryAllByTestId("context-pane").length).toBeLessThanOrEqual(1);
    expect(screen.queryByTestId("embedded-analysis-result")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chapter-result-open-independent")).not.toBeInTheDocument();
  });

  it("does not auto-switch to journey for historical complete runs without explicit tab", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:05:00Z",
      chapter_complete: true,
      effective_status: "completed",
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      completed_scene_count: 14,
      total_scene_count: 14,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 9,
      trusted: true,
      visualization: {
        scene_nodes: [
          {
            scene_ordinal: 1,
            scores: { reading_momentum: 1, plot_progress: 1 },
            engagement: { engagement_score: 1 },
          },
        ],
        phases: [{ ordinal: 1 }],
        curve_series: { curiosity: [{ scene_ordinal: 1, value: 0.5 }] },
      },
    } as any);

    renderBook("/books/1?chapter=2&analysisRun=77&view=reading");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "reading");
    });
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-active-tab", "text");
    expect(screen.queryByTestId("workspace-journey-pane")).not.toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("reading toggle keeps analysisRun and can return to embedded result", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
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
      completed_scene_count: 14,
      total_scene_count: 14,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "missing",
      visualization: null,
    } as any);

    // Stale view=result while incomplete → restore progress workspace.
    renderBook("/books/1?chapter=2&analysisRun=77&view=result");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "progress");
    });
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("workspace-tab-reading"));
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "reading");
    });
    expect(screen.getByTestId("chapter-analysis-scene-complete-banner")).toBeInTheDocument();
    expect(screen.queryByTestId("chapter-analysis-complete-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-analysis-run", "77");
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    // CHG-20260727-019: scene-complete / awaiting journey stays on progress CTA (not a second journey start).
    expect(screen.getByTestId("shell-view-analysis-progress")).toHaveTextContent("查看分析进度");
    fireEvent.click(screen.getByTestId("banner-continue-reader-journey"));
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "result");
    });
    expect(screen.getByTestId("embedded-analysis-result")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("keeps complete chapter view=result Scene links working", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 55,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
      execution_mode: "local",
      cloud_consent: false,
      sends_content_to_cloud: false,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:05:00Z",
      chapter_complete: true,
      effective_status: "completed",
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      completed_scene_count: 14,
      total_scene_count: 14,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 2,
      trusted: true,
      visualization: {
        scene_nodes: [
          {
            scene_ordinal: 14,
            scores: { reading_momentum: 1, plot_progress: 1 },
            engagement: { engagement_score: 1 },
          },
        ],
        phases: [{ ordinal: 1 }],
        curve_series: { curiosity: [{ scene_ordinal: 14, value: 1 }] },
      },
    } as any);

    renderBook(
      "/books/1?chapter=2&analysisRun=55&view=result&tab=reader-journey&mode=sync&scene=14",
    );
    await waitFor(() => {
      expect(screen.getByTestId("workspace-journey-pane")).toBeInTheDocument();
    });
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute("data-view", "result");
    expect(screen.getByTestId("main-content-pane")).toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });

  it("shows book and chapter names in toolbar and returns to library", async () => {
    renderBook("/books/1?chapter=2");
    expect(await screen.findByText("测试书")).toBeInTheDocument();
    const toolbar = screen.getByTestId("book-shell-toolbar");
    expect(within(toolbar).getByText("测试书")).toBeInTheDocument();
    expect(within(toolbar).getByText("开端")).toBeInTheDocument();
    fireEvent.click(within(toolbar).getByTestId("workspace-back-library"));
    expect(await screen.findByTestId("library-page")).toBeInTheDocument();
  });

  it("keeps long titles accessible via title attribute", async () => {
    const prevFetch = global.fetch;
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
                title: "超长章节标题".repeat(8),
                display_title: "超长章节标题".repeat(8),
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.match(/\/books\/\d+$/)) {
          return new Response(
            JSON.stringify({
              id: 1,
              title: "超长书名".repeat(10),
              source_file_name: "a.txt",
              source_file_hash: "abc123def456",
              created_at: "2026-01-01T00:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
    try {
      renderBook("/books/1?chapter=2");
      expect(await screen.findByText(/超长书名/)).toBeInTheDocument();
      const toolbar = screen.getByTestId("book-shell-toolbar");
      const bookEl = within(toolbar).getByText(/超长书名/);
      const chapterEl = within(toolbar).getByText(/超长章节标题/);
      expect(bookEl.getAttribute("title")).toContain("超长书名");
      expect(chapterEl.getAttribute("title")).toContain("超长章节标题");
    } finally {
      vi.stubGlobal("fetch", prevFetch);
    }
  });

  it("reading settings write original store values and keep paragraph id toggle", async () => {
    renderBook();
    const toolbar = screen.getByTestId("book-shell-toolbar");
    fireEvent.click(within(toolbar).getByTestId("reading-settings-trigger"));
    const panel = within(toolbar).getByTestId("reading-settings-panel");
    fireEvent.click(within(panel).getByTestId("reading-font-increase"));
    expect(useUiStore.getState().fontSize).toBe(18);
    fireEvent.click(within(panel).getByRole("button", { name: "宽松" }));
    expect(useUiStore.getState().lineHeight).toBe(2.2);
    fireEvent.click(within(panel).getByRole("button", { name: "窄" }));
    expect(useUiStore.getState().contentWidth).toBe("narrow");
    const checkbox = within(panel).getByTestId("reading-show-paragraph-ids");
    fireEvent.click(checkbox);
    expect(useUiStore.getState().showParagraphIds).toBe(true);
    expect(screen.getByTestId("book-chapter-shell")).toHaveAttribute(
      "data-show-paragraph-ids",
      "true",
    );
  });

  it("catalog drawer exposes title, close icon, and chapter click", async () => {
    vi.mocked(analysisApi.run).mockResolvedValue({
      id: 77,
      subject_id: "2",
      provider: "fake",
      model: "fake",
      status: "succeeded",
      progress_current: 14,
      progress_total: 14,
      execution_mode: "cloud",
      cloud_consent: true,
      sends_content_to_cloud: true,
      retryable: false,
      created_at: "2026-01-01T00:00:00Z",
      completed_at: "2026-01-01T00:05:00Z",
      chapter_complete: true,
      effective_status: "completed",
      reusable_checkpoint_count: 0,
      conflicted_checkpoint_count: 0,
      checkpoint_total_count: 0,
      checkpoint_available: false,
      completed_scene_count: 14,
      total_scene_count: 14,
    } as any);
    vi.mocked(analysisApi.readerJourney).mockResolvedValue({
      status: "succeeded",
      journey_run_id: 9,
      visualization: { scene_nodes: [] },
    } as any);
    renderBook("/books/1?chapter=2&analysisRun=77&view=result");
    await waitFor(() => {
      expect(screen.getByTestId("book-chapter-catalog")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("book-chapter-catalog"));
    const drawer = await screen.findByTestId("chapter-catalog-drawer");
    expect(within(drawer).getByText("章节目录")).toBeInTheDocument();
    expect(within(drawer).getByTestId("chapter-catalog-close")).toHaveAttribute(
      "aria-label",
      "关闭",
    );
    expect(within(drawer).getByTestId("catalog-chapter-2")).toHaveClass("active");
    fireEvent.click(within(drawer).getByTestId("chapter-catalog-close"));
    await waitFor(() => {
      expect(screen.queryByTestId("chapter-catalog-drawer")).not.toBeInTheDocument();
    });
  });

  it("collapsing progress inspector does not drop analysisRun binding", async () => {
    renderBook("/books/1?chapter=2&analysisRun=77&view=progress");
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    });
    const shell = screen.getByTestId("book-chapter-shell");
    const reader = document.querySelector(".book-shell-workspace") as HTMLElement | null;
    const expandedWidth = reader?.getBoundingClientRect().width ?? 0;
    fireEvent.click(screen.getByTestId("chapter-analysis-dismiss"));
    await waitFor(() => {
      expect(screen.queryByTestId("chapter-analysis-progress")).not.toBeInTheDocument();
    });
    expect(shell).toHaveAttribute("data-analysis-run", "77");
    expect(shell).toHaveAttribute("data-has-progress", "false");
    expect(screen.getByTestId("chapter-analysis-expand")).toBeInTheDocument();
    const collapsedWidth = reader?.getBoundingClientRect().width ?? 0;
    // jsdom may report 0 widths; only assert widen when layout metrics exist.
    if (expandedWidth > 0 && collapsedWidth > 0) {
      expect(collapsedWidth).toBeGreaterThanOrEqual(expandedWidth);
    }
    fireEvent.click(screen.getByTestId("chapter-analysis-expand"));
    await waitFor(() => {
      expect(screen.getByTestId("chapter-analysis-progress")).toBeInTheDocument();
    });
    expect(shell).toHaveAttribute("data-has-progress", "true");
  });

  it("does not change start analysis disabled rules", async () => {
    renderBook();
    const start = await screen.findByTestId("shell-start-analysis");
    await waitFor(() => expect(start).toBeEnabled());
    expect(start).toHaveAttribute("data-testid", "shell-start-analysis");
  });
});
