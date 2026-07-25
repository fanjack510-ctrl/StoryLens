import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { BookRoutePage } from "../pages/BookRoutePage";
import { WholeBookInsightsPage } from "../pages/WholeBookInsightsPage";
import * as wholeBookInsightsApiMod from "../services/wholeBookInsightsApi";

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

describe("Whole-Book Insights desktop entry", () => {
  beforeEach(() => {
    fetchSpy.mockReset();
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
              features: { pro_whole_book_insights: false },
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
          return new Response(
            JSON.stringify({ id: 1, title: "测试书" }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
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
        return new Response(JSON.stringify({}), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it("free entry shows upgrade prompt and does not fetch insights API", async () => {
    renderWithRouter(<BookRoutePage />);
    const entry = await screen.findByTestId("whole-book-insights-entry-free");
    await fireEvent.click(entry);
    expect(await screen.findByTestId("whole-book-insights-upgrade-prompt")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("pro entry renders coverage on insights page", async () => {
    fetchSpy.mockResolvedValue({
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
      chapters: [],
      computed_at: "2026-07-25T00:00:00Z",
    });

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo) => {
        const href = String(input);
        if (href.includes("/api/v1/entitlements")) {
          return new Response(
            JSON.stringify({
              edition: "pro",
              edition_label: "专业版",
              pro_active: true,
              features: { pro_whole_book_insights: true },
            }),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        if (href.includes("/api/v1/books/1") && !href.includes("whole-book-insights")) {
          return new Response(JSON.stringify({ id: 1, title: "测试书" }), {
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

    renderWithRouter(<WholeBookInsightsPage />, "/books/1/whole-book-insights");
    await waitFor(() => expect(fetchSpy).toHaveBeenCalledWith(1));
    expect(await screen.findByTestId("whole-book-insights-coverage")).toHaveTextContent(
      "有效章节 1 / 2",
    );
    expect(screen.getByTestId("whole-book-insights-journey-curve")).toBeInTheDocument();
  });
});
