import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analysisApi } from "../../services/analysisApi";
import { EmbeddedAnalysisResultShell } from "./EmbeddedAnalysisResultShell";

vi.mock("../../services/analysisApi", async () => {
  const actual = await vi.importActual<typeof import("../../services/analysisApi")>(
    "../../services/analysisApi",
  );
  return {
    analysisApi: {
      ...actual.analysisApi,
      results: vi.fn(),
      readerJourney: vi.fn(async () => ({ status: "missing", visualization: null })),
      sceneParagraphs: vi.fn(async () => ({ paragraphs: [] })),
    },
  };
});

vi.mock("./AnalysisResultRouteAdapter", () => ({
  AnalysisResultRouteAdapter: ({ runId }: { runId: number }) => (
    <div data-testid="mock-result-adapter">adapter:{runId}</div>
  ),
}));

beforeEach(() => {
  vi.mocked(analysisApi.results).mockReset();
});

afterEach(cleanup);

function renderShell(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/books/:bookId"
            element={
              <EmbeddedAnalysisResultShell runId={55} onReading={() => undefined} />
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EmbeddedAnalysisResultShell", () => {
  it("loads Scene Analysis results into embedded adapter", async () => {
    vi.mocked(analysisApi.results).mockResolvedValue({
      run: { id: 55, status: "succeeded", provider: "fake", model: "fake" },
      chapter: { id: 2, book_id: 1, title: "开端", display_title: "开端" },
      boundary_revision: null,
      summary: { total_scene_count: 1 },
      scenes: [],
    } as any);

    renderShell("/books/1?chapter=2&analysisRun=55&view=result");
    expect(screen.getByTestId("chapter-result-loading")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("embedded-analysis-result")).toBeInTheDocument();
    });
    expect(screen.getByTestId("mock-result-adapter")).toHaveTextContent("adapter:55");
    expect(analysisApi.results).toHaveBeenCalledWith(55);
  });

  it("shows error without independent result-page escape hatch", async () => {
    vi.mocked(analysisApi.results).mockRejectedValue(new Error("boom"));
    renderShell("/books/1?chapter=2&analysisRun=55&view=result");
    await waitFor(
      () => {
        expect(screen.getByTestId("chapter-result-error")).toBeInTheDocument();
      },
      { timeout: 4000 },
    );
    expect(screen.queryByTestId("chapter-result-open-independent")).not.toBeInTheDocument();
    expect(screen.getByTestId("chapter-result-retry")).toBeInTheDocument();
    expect(screen.getByTestId("chapter-result-back-reading")).toBeInTheDocument();
  });
});
