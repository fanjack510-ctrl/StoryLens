import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BookRoutePage } from "../pages/BookRoutePage";
import { WholeBookInsightsPage } from "../pages/WholeBookInsightsPage";
import * as wholeBookInsightsApiMod from "../services/wholeBookInsightsApi";
import type { WholeBookInsightsChapterRow, WholeBookInsightsResult } from "../services/wholeBookInsightsApi";

vi.mock("../services/productEdition", async () => {
  const actual = await vi.importActual<typeof import("../services/productEdition")>(
    "../services/productEdition",
  );
  return {
    ...actual,
    // Existing page tests need shipped=true; release-scope test overrides via dynamic import if needed.
    PRO_CAPABILITIES_SHIPPED: true,
  };
});

const fetchSpy = vi.spyOn(wholeBookInsightsApiMod.wholeBookInsightsApi, "fetch");

function renderWithRouter(ui: React.ReactElement, initial = "/books/1?chapter=2&view=reading") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route path="/books/:bookId" element={<BookRoutePage />} />
          <Route path="/books/:bookId/whole-book-insights" element={<WholeBookInsightsPage />} />
          <Route path="/settings" element={<div>settings-page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function stubEntitlements(isPro: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo) => {
      const href = String(input);
      if (href.includes("/api/v1/entitlements")) {
        return new Response(
          JSON.stringify({
            edition: isPro ? "pro" : "free",
            edition_label: isPro ? "专业版" : "免费版",
            pro_active: isPro,
            features: { pro_whole_book_insights: isPro },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (href.includes("/api/v1/books/1")) {
        if (href.includes("/chapters")) {
          return new Response(
            JSON.stringify([
              {
                id: 2,
                book_id: 1,
                chapter_index: 1,
                title: "第1章",
                display_title: "第1章",
                section_type: "chapter",
              },
            ]),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (!href.includes("whole-book-insights")) {
          return new Response(JSON.stringify({ id: 1, title: "测试书" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }
      }
      if (href.includes("/api/v1/analysis-runs")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (href.includes("/api/v1/chapters/")) {
        return new Response(
          JSON.stringify({ items: [], offset: 0, limit: 200, total: 0, has_more: false }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(JSON.stringify({ error_code: "HTTP_ERROR" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
}

function makeChapter(
  id: number,
  index: number,
  isValid: boolean,
): WholeBookInsightsChapterRow {
  return {
    chapter_id: id,
    chapter_index: index,
    chapter_title: `第${index}章`,
    display_title: `第${index}章`,
    analysis_run_id: isValid ? 100 + id : null,
    effective_status: isValid ? "completed" : null,
    completed_at: isValid ? "2026-07-25T00:00:00Z" : null,
    is_valid: isValid,
    scenes: isValid
      ? [
          {
            scene_id: id * 10,
            scene_ordinal: 1,
            tension_score: 50,
            hook_score: 60,
            payoff_score: 40,
            hooks: [],
            payoffs: [],
            risk_points: [],
            evidence_paragraph_ids: [],
            function_tags: [],
            deep_link: {
              chapter_id: id,
              scene_id: id * 10,
              paragraph_id: `p-${id}`,
            },
          },
        ]
      : [],
  };
}

function baseInsights(overrides: Partial<WholeBookInsightsResult> = {}): WholeBookInsightsResult {
  return {
    schema: "storylens.whole_book_insights.result.v1",
    book_id: 1,
    coverage: { total_chapters: 2, valid_chapters: 1, invalid_chapters: 1 },
    journey_curve: [{ chapter_index: 1, tension: 50, hook: 60, payoff: 40 }],
    pacing: { summary: "test pacing" },
    peaks: [],
    valleys: [],
    hooks: [],
    payoffs: [],
    functions: [],
    diagnostics: [],
    chapters: [makeChapter(2, 1, true), makeChapter(3, 2, false)],
    computed_at: "2026-07-25T00:00:00Z",
    ...overrides,
  };
}

describe("Whole-Book Insights desktop entry", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    fetchSpy.mockReset();
    stubEntitlements(false);
  });

  // 原来这里是两条：开发者模式开、开发者模式关，各断言一次入口不出现。开发者模式删掉之后，
  // 那两条问的是同一个问题——入口在书页面上永远不出现，没有「除非…」。
  it("book workspace never shows chapter aggregation entry (1.1.0 release scope)", async () => {
    renderWithRouter(<BookRoutePage />);
    await screen.findByTestId("shell-start-analysis");
    expect(screen.queryByTestId("whole-book-insights-entry-free")).not.toBeInTheDocument();
    expect(screen.queryByTestId("whole-book-insights-entry-pro")).not.toBeInTheDocument();
    expect(screen.queryByText("章节聚合洞察")).not.toBeInTheDocument();
    expect(screen.queryByText("章节聚合洞察 Pro")).not.toBeInTheDocument();
  });

  it("pro page uses chapter aggregation title and coverage copy", async () => {
    fetchSpy.mockResolvedValue(baseInsights());
    stubEntitlements(true);

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(1));

    const page = await screen.findByTestId("whole-book-insights-page");
    expect(within(page).getByRole("heading", { level: 1 })).toHaveTextContent("章节聚合洞察");
    expect(page).not.toHaveTextContent("全书洞察");

    const coverage = screen.getByTestId("whole-book-insights-coverage");
    expect(coverage).toHaveTextContent("已完成精细单章分析：1 / 2 章");
    expect(coverage).toHaveTextContent("章节资产覆盖率：50%");
    expect(coverage).not.toHaveTextContent("有效章节");
    expect(coverage).not.toHaveTextContent("原文未覆盖");
    expect(screen.getByTestId("whole-book-insights-coverage-note")).toHaveTextContent(
      "不是原文覆盖",
    );
    expect(screen.getByTestId("whole-book-insights-journey-curve")).toBeInTheDocument();
  });

  it("explains low coverage as dependency on single-chapter analysis", async () => {
    const chapters = Array.from({ length: 8 }, (_, i) => makeChapter(i + 1, i + 1, i === 0));
    fetchSpy.mockResolvedValue(
      baseInsights({
        coverage: { total_chapters: 8, valid_chapters: 1, invalid_chapters: 7 },
        chapters,
      }),
    );
    stubEntitlements(true);

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    const notice = await screen.findByTestId("whole-book-insights-low-coverage");
    expect(notice).toHaveTextContent("单章精细分析");
    expect(notice).toHaveTextContent("不代表系统故障");
    expect(notice).not.toHaveTextContent("原文未覆盖");
    expect(notice).not.toHaveTextContent("全书原生分析完成");
  });

  it("collapses long missing chapter list by default", async () => {
    const chapters = [
      makeChapter(1, 1, true),
      ...Array.from({ length: 35 }, (_, i) => makeChapter(i + 2, i + 2, false)),
    ];
    fetchSpy.mockResolvedValue(
      baseInsights({
        coverage: { total_chapters: 36, valid_chapters: 1, invalid_chapters: 35 },
        chapters,
      }),
    );
    stubEntitlements(true);

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    const missing = await screen.findByTestId("whole-book-insights-missing-chapters");
    expect(missing).toHaveTextContent("尚未完成精细单章分析（35）");
    expect(within(missing).getAllByRole("listitem")).toHaveLength(20);
    expect(screen.queryByText("第35章")).not.toBeInTheDocument();

    await fireEvent.click(screen.getByTestId("whole-book-insights-missing-toggle"));
    expect(within(missing).getAllByRole("listitem")).toHaveLength(35);
    expect(screen.getByText("第35章", { exact: false })).toBeInTheDocument();
  });

  it("keeps raw diagnostics JSON collapsed under developer details", async () => {
    const raw = { code: "ASSET_GAP", message: "缺少旅程", detail: { nested: true } };
    fetchSpy.mockResolvedValue(baseInsights({ diagnostics: [raw] }));
    stubEntitlements(true);

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    await screen.findByTestId("whole-book-insights-diagnostics");
    expect(screen.getByTestId("whole-book-insights-diagnostics-summary")).toHaveTextContent(
      "ASSET_GAP：缺少旅程",
    );
    const details = screen.getByTestId("whole-book-insights-diagnostics-details");
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText("开发者详情")).toBeInTheDocument();
    // Raw JSON lives under details but is not the default visible summary surface.
    expect(details.querySelector("pre")?.textContent).toContain('"nested": true');
  });

  it("preserves chapter deep link to analysis result", async () => {
    fetchSpy.mockResolvedValue(baseInsights());
    stubEntitlements(true);

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    const link = await screen.findByTestId("whole-book-insights-chapter-link-2");
    expect(link).toHaveAttribute("href", expect.stringContaining("/books/1?"));
    expect(link).toHaveAttribute("href", expect.stringContaining("chapter=2"));
    expect(link).toHaveAttribute("href", expect.stringContaining("view=result"));
    expect(link).toHaveAttribute("href", expect.stringContaining("analysisRun=102"));
    expect(link).toHaveAttribute("href", expect.stringContaining("scene=20"));
  });
});
