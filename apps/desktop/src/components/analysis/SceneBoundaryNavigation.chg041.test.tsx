import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mapUrlToActiveTab } from "../../services/resolveWorkspaceLayout";

vi.mock("../../services/analysisApi", () => ({
  analysisApi: {
    sceneBoundariesOverview: vi.fn(async () => ({
      chapter_id: 1,
      chapter_text_hash: "h",
      confirmed_revision: null,
      draft_revision: {
        revision_id: 2,
        revision_number: 1,
        status: "draft",
        source: "user",
        revision_etag: "e",
        boundary_hash: "b",
        chapter_text_hash: "h",
        scenes: [],
      },
      model_revision: null,
      awaiting_confirmation: false,
    })),
    readerJourney: vi.fn(async () => {
      throw Object.assign(new Error("missing"), { code: "NOT_FOUND" });
    }),
  },
}));

describe("CHG-041 navigation helpers", () => {
  afterEach(() => cleanup());

  it("maps scene-boundary-review view away from journey tab", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "scene-boundary-review",
        requestedTab: "reader-journey",
        chapterComplete: false,
        journeyAvailable: false,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("scene");
  });

  it("keeps reader-journey tab as journey when not on boundary review view", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "result",
        requestedTab: "reader-journey",
        chapterComplete: true,
        journeyAvailable: true,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("journey");
  });
});

describe("reader journey gate copy", () => {
  afterEach(() => cleanup());

  it("renders unconfirmed journey gate card", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    function Gate() {
      return (
        <div>
          <h1>阅读旅程尚未开始</h1>
          <p>请先确认场景边界，StoryLens 将按照确认后的场景进行旅程分析。</p>
          <button type="button" data-testid="reader-journey-go-confirm-scenes">
            去确认场景
          </button>
        </div>
      );
    }
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/books/1?tab=reader-journey"]}>
          <Routes>
            <Route path="/books/:bookId" element={<Gate />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByText("阅读旅程尚未开始")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("reader-journey-go-confirm-scenes"));
  });
});
