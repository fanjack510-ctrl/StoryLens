import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AnalysisResultsShellPage } from "./AnalysisResultsShellPage";

const globalCss = readFileSync(resolve(__dirname, "../styles/global.css"), "utf8");
const syncCss = readFileSync(
  resolve(__dirname, "../components/readerJourney/syncWorkspace.css"),
  "utf8",
);

vi.mock("./AnalysisResultsPage", () => ({
  AnalysisResultsPage: () => (
    <section className="workspace results-page" data-testid="analysis-results-inner">
      <aside className="analysis-pane">
        <div className="tabs">
          <button type="button" data-testid="tab-structure">
            场景结构
          </button>
          <button type="button" data-testid="tab-evidence">
            证据
          </button>
          <button type="button" data-testid="tab-history">
            历史
          </button>
          <button type="button" data-testid="tab-overview">
            整章概览
          </button>
          <button type="button" data-testid="tab-journey">
            读者旅程
          </button>
        </div>
        <div className="export-bar">
          <button type="button" data-testid="export-json">
            导出JSON
          </button>
          <button type="button" data-testid="export-markdown">
            导出Markdown
          </button>
          <button type="button" data-testid="generate-reader-journey">
            查看读者旅程
          </button>
        </div>
      </aside>
      <div className="journey-sync-workspace" data-testid="journey-sync-workspace">
        <header className="journey-sync-sticky-bar">
          <h1 className="journey-sync-title">旅程分析</h1>
          <div className="journey-sync-tabs tabs">
            <button type="button" data-testid="tab-structure-sync">
              场景结构
            </button>
            <button type="button" data-testid="tab-journey-sync">
              读者旅程
            </button>
          </div>
          <div className="journey-sync-mode-toggle">
            <button type="button" data-testid="journey-mode-sync">
              同步
            </button>
            <button type="button" data-testid="journey-mode-journey">
              旅程
            </button>
            <button type="button" data-testid="journey-mode-reading">
              正文
            </button>
          </div>
          <div className="journey-sync-actions">
            <button type="button" data-testid="open-scene-structure-drawer">
              章节结构
            </button>
          </div>
          <div className="export-bar journey-sync-export-bar">
            <button type="button" data-testid="export-journey-json">
              导出旅程JSON
            </button>
            <button type="button" data-testid="journey-export-png">
              导出PNG
            </button>
          </div>
        </header>
      </div>
    </section>
  ),
}));

async function defaultShellFetch(input: RequestInfo | URL) {
  const href = String(input);
  if (href.includes("/results")) {
    return new Response(
      JSON.stringify({
        run: {
          id: 55,
          status: "succeeded",
          provider: "aliyun_qwen_plus",
          model: "qwen-plus",
          prompt_version: "v3.5",
          schema_version: "1",
          analysis_mode: "assisted_boundary_review",
          execution_mode: "cloud",
        },
        chapter: { id: 2, book_id: 1, chapter_index: 1, title: "第二章" },
        boundary_revision: null,
        summary: {
          total_scene_count: 0,
          single_paragraph_scene_count: 0,
          longest_scene_paragraph_count: 0,
          manual_added_boundary_count: 0,
          model_accepted_boundary_count: 0,
          user_accepted_conflict_count: 0,
          artifact_coverage_rate: 0,
          evidence_coverage_rate: 0,
          offline_recovered_scene_count: 0,
        },
        scenes: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }
  if (href.includes("reader-journey")) {
    return new Response(
      JSON.stringify({
        journey_run_id: 2,
        analysis_run_id: 55,
        status: "succeeded",
        formula_version: "1.0",
        visualization: { visualization_version: "1.1", scene_nodes: [] },
        phases: [],
        scene_profiles: [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }
  if (href.includes("/books/")) {
    return new Response(JSON.stringify({ id: 1, title: "书" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }
  return new Response(JSON.stringify({}), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

vi.stubGlobal("fetch", vi.fn(defaultShellFetch));

function renderShell(path = "/analysis-runs/55/results") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/analysis-runs/:runId/results" element={<AnalysisResultsShellPage />} />
          <Route path="/books/:bookId" element={<div>章节页</div>} />
          <Route path="/tasks" element={<div>任务</div>} />
          <Route path="/library" element={<div>书库</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Analysis results shell", () => {
  afterEach(() => {
    cleanup();
    vi.mocked(fetch).mockImplementation(defaultShellFetch);
  });

  it("keeps at most four primary toolbar actions and reuses results page", async () => {
    renderShell();
    const shell = await screen.findByTestId("results-shell");
    await waitFor(() => expect(shell).toHaveAttribute("data-results-state", "completed"));
    expect(shell).toHaveAttribute("data-primary-actions", "4");
    expect(shell).toHaveAttribute("data-shell-mode", "analysis");
    expect(shell).toHaveAttribute("data-result-view", "analysis");
    expect(screen.getByTestId("back-to-chapter")).toBeInTheDocument();
    expect(screen.getByTestId("result-view-analysis")).toBeInTheDocument();
    expect(screen.getByTestId("result-view-journey")).toBeInTheDocument();
    expect(screen.getByTestId("results-more-menu-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("analysis-results-inner")).toBeInTheDocument();
    expect(screen.queryByTestId("results-tech-info")).not.toBeInTheDocument();
  });

  it("shows incomplete empty state when results payload has no run.status", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const href = String(input);
      if (href.includes("/results")) {
        return new Response(JSON.stringify({ scenes: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderShell();
    const shell = await screen.findByTestId("results-shell");
    await waitFor(() => expect(shell).toHaveAttribute("data-results-state", "incomplete"));
    expect(await screen.findByTestId("results-empty-incomplete")).toHaveTextContent(
      /分析结果数据不完整/,
    );
    expect(screen.queryByText("Unexpected Application Error")).not.toBeInTheDocument();
  });

  it("shows incomplete empty state for empty object payload", async () => {
    vi.mocked(fetch).mockImplementation(async () => {
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderShell();
    expect(await screen.findByTestId("results-empty-incomplete")).toBeInTheDocument();
  });

  it("shows failed state when run.status is not succeeded", async () => {
    vi.mocked(fetch).mockImplementation(async (input: RequestInfo | URL) => {
      const href = String(input);
      if (href.includes("/results")) {
        return new Response(
          JSON.stringify({
            run: {
              id: 55,
              status: "failed",
              provider: "aliyun_qwen_plus",
              model: "qwen-plus",
              prompt_version: "v3.5",
              schema_version: "1",
              analysis_mode: "assisted_boundary_review",
              execution_mode: "cloud",
            },
            chapter: { id: 2, book_id: 1, chapter_index: 1, title: "第二章" },
            boundary_revision: null,
            summary: {
              total_scene_count: 0,
              single_paragraph_scene_count: 0,
              longest_scene_paragraph_count: 0,
              manual_added_boundary_count: 0,
              model_accepted_boundary_count: 0,
              user_accepted_conflict_count: 0,
              artifact_coverage_rate: 0,
              evidence_coverage_rate: 0,
              offline_recovered_scene_count: 0,
            },
            scenes: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({}), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    renderShell();
    const shell = await screen.findByTestId("results-shell");
    await waitFor(() => expect(shell).toHaveAttribute("data-results-state", "failed"));
    expect(await screen.findByTestId("results-empty-failed")).toHaveTextContent(/failed/);
  });

  it("analysis view CSS hides legacy journey tab and resident export buttons", async () => {
    expect(globalCss).toContain('[data-testid="tab-history"]');
    expect(globalCss).toContain('[data-testid="tab-journey"]');
    expect(globalCss).toContain(".results-shell-simplified.is-analysis .analysis-pane > .export-bar");
    expect(globalCss).not.toMatch(
      /\.results-shell-simplified[^{]*\{[^}]*nth-(child|of-type)/,
    );
    renderShell();
    await waitFor(() =>
      expect(screen.getByTestId("results-shell")).toHaveAttribute("data-results-state", "completed"),
    );
    const shell = screen.getByTestId("results-shell");
    expect(shell.className).toContain("is-analysis");
    expect(screen.getByTestId("tab-structure")).toBeInTheDocument();
    expect(screen.getByTestId("tab-evidence")).toBeInTheDocument();
    expect(screen.getByTestId("tab-overview")).toBeInTheDocument();
    // Legacy controls remain mounted for More-menu proxy clicks
    expect(screen.getByTestId("tab-history")).toBeInTheDocument();
    expect(screen.getByTestId("export-json")).toBeInTheDocument();
  });

  it("journey view CSS keeps three modes and hides legacy result chrome", async () => {
    expect(globalCss).toContain(".results-shell-simplified.is-journey .journey-sync-tabs");
    expect(globalCss).toContain(".results-shell-simplified.is-journey .journey-sync-export-bar");
    expect(syncCss).toContain(".results-shell-simplified.is-journey .journey-sync-tabs");
    expect(syncCss).toContain('content: "正文与旅程"');
    renderShell("/analysis-runs/55/results?tab=reader-journey");
    await waitFor(() =>
      expect(screen.getByTestId("results-shell")).toHaveAttribute("data-results-state", "completed"),
    );
    const shell = screen.getByTestId("results-shell");
    expect(shell).toHaveAttribute("data-shell-mode", "journey");
    expect(shell.className).toContain("is-journey");
    expect(screen.getByTestId("journey-mode-sync")).toBeInTheDocument();
    expect(screen.getByTestId("journey-mode-journey")).toBeInTheDocument();
    expect(screen.getByTestId("journey-mode-reading")).toBeInTheDocument();
    expect(document.querySelector(".journey-sync-tabs")).toBeTruthy();
    expect(document.querySelector(".journey-sync-export-bar")).toBeTruthy();
  });

  it("keeps export and history available via more menu", async () => {
    renderShell();
    await screen.findByTestId("results-shell");
    fireEvent.click(screen.getByTestId("results-more-menu-trigger"));
    const menu = screen.getByTestId("results-more-menu");
    expect(within(menu).getByTestId("results-more-export-json")).toBeInTheDocument();
    expect(within(menu).getByTestId("results-more-export-md")).toBeInTheDocument();
    expect(within(menu).getByTestId("results-more-export-journey-json")).toBeInTheDocument();
    expect(within(menu).getByTestId("results-more-history")).toBeInTheDocument();
    expect(within(menu).getByTestId("results-more-structure")).toBeInTheDocument();
  });
});
