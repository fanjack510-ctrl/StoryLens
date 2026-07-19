import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useParams, useSearchParams } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

function FakeResultsPage() {
  const params = useParams();
  const [sp] = useSearchParams();
  return (
    <div data-testid="fake-results-page">
      run:{params.runId}|scene:{sp.get("scene") || ""}|tab:{sp.get("tab") || ""}|chapter:
      {sp.get("chapter") || ""}
    </div>
  );
}

vi.mock("../../pages/AnalysisResultsPage", () => ({
  AnalysisResultsPage: FakeResultsPage,
}));

import { AnalysisResultRouteAdapter } from "./AnalysisResultRouteAdapter";

afterEach(cleanup);

describe("AnalysisResultRouteAdapter", () => {
  it("injects runId while reading parent book search params", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter
          initialEntries={[
            "/books/1?chapter=2&analysisRun=55&view=result&tab=reader-journey&mode=sync&scene=14",
          ]}
        >
          <Routes>
            <Route path="/books/:bookId" element={<AnalysisResultRouteAdapter runId={55} />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const el = screen.getByTestId("fake-results-page");
    expect(el).toHaveTextContent("run:55");
    expect(el).toHaveTextContent("scene:14");
    expect(el).toHaveTextContent("tab:reader-journey");
    expect(el).toHaveTextContent("chapter:2");
  });
});
