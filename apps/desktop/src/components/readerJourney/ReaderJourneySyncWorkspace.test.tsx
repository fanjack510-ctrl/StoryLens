import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ReaderJourneySyncWorkspace } from "./ReaderJourneySyncWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { booksApi } from "../../services/booksApi";
import type { SceneResultItem } from "../../types";

vi.mock("../../services/booksApi", () => ({
  booksApi: {
    paragraphs: vi.fn(),
  },
}));

afterEach(cleanup);

function makeScene(ordinal: number): SceneResultItem {
  const start = `B0001-C0002-P${String(ordinal === 14 ? 64 : ordinal * 10).padStart(4, "0")}`;
  const end =
    ordinal === 14
      ? "B0001-C0002-P0068"
      : `B0001-C0002-P${String(ordinal * 10 + 2).padStart(4, "0")}`;
  return {
    scene: {
      id: ordinal,
      scene_key: `S${ordinal}`,
      ordinal,
      start_paragraph_id: start,
      end_paragraph_id: end,
      paragraph_count: 3,
      is_single_paragraph: false,
      boundary_source: "model_accepted",
      boundary_revision_id: 1,
      boundary_detected: true,
      boundary_confidence: 0.9,
    },
    analysis_artifact: null,
    evidence: [],
    illegal_evidence: [],
    revision: null,
  };
}

describe("ReaderJourneySyncWorkspace", () => {
  const visualization = buildMockReaderJourneyVisualization();
  const scenes = Array.from({ length: 14 }, (_, i) => makeScene(i + 1));

  beforeEach(() => {
    vi.mocked(booksApi.paragraphs).mockResolvedValue({
      items: Array.from({ length: 80 }, (_, i) => ({
        id: `B0001-C0002-P${String(i + 1).padStart(4, "0")}`,
        chapter_id: 2,
        paragraph_index: i + 1,
        raw_text: `段落 ${i + 1}`,
      })),
      offset: 0,
      limit: 500,
      total: 80,
      has_more: false,
    });
  });

  it("renders sync workspace with split pane and no scene list", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/?tab=reader-journey&mode=sync&scene=14"]}>
          <ReaderJourneySyncWorkspace
            chapterId={2}
            chapterTitle="第1章 戏鬼回家"
            scenes={scenes}
            visualization={visualization}
            tab="journey"
            onTabChange={vi.fn()}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("journey-sync-workspace")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-list")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("journey-workspace-grid")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId("structured-chapter-text-pane")).toBeInTheDocument());
    expect(screen.getByTestId("journey-workspace")).toBeInTheDocument();
    expect(screen.getByTestId("journey-source-pane")).toBeInTheDocument();
  });
});
