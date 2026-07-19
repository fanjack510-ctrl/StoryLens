import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { analysisApi } from "../../services/analysisApi";
import { AnalysisResultRouteAdapter } from "./AnalysisResultRouteAdapter";

vi.mock("../../services/analysisApi", async () => {
  const actual = await vi.importActual<typeof import("../../services/analysisApi")>(
    "../../services/analysisApi",
  );
  return {
    analysisApi: {
      ...actual.analysisApi,
      results: vi.fn(),
      sceneParagraphs: vi.fn(),
      readerJourney: vi.fn(async () => ({ status: "missing", visualization: null })),
      createReaderJourney: vi.fn(),
      readerJourneyPreflight: vi.fn(),
    },
  };
});

const scenePayload = {
  run: {
    id: 55,
    status: "succeeded",
    provider: "fake",
    model: "fake",
    created_at: "2026-01-01T00:00:00Z",
  },
  chapter: { id: 2, book_id: 1, title: "开端", display_title: "开端" },
  boundary_revision: null,
  summary: {
    total_scene_count: 2,
    single_paragraph_scene_count: 0,
    longest_scene_ordinal: 1,
    longest_scene_paragraph_count: 1,
  },
  scenes: [
    {
      scene: {
        id: 101,
        ordinal: 1,
        scene_key: "S01",
        start_paragraph_id: "B0001-C0002-P0001",
        end_paragraph_id: "B0001-C0002-P0001",
        is_single_paragraph: true,
        boundary_source: "章末",
      },
      fields: {
        goal: { summary: "目标一", evidence_paragraph_ids: ["B0001-C0002-P0001"] },
      },
      evidence: [
        {
          field_path: "goal.evidence",
          group: "goal",
          paragraph_id: "B0001-C0002-P0001",
          in_scope: true,
          order_index: 1,
        },
      ],
      illegal_evidence: [],
      analysis_artifact: {
        id: 201,
        analysis: {
          goal: { summary: "目标一", evidence_paragraph_ids: ["B0001-C0002-P0001"] },
        },
      },
    },
    {
      scene: {
        id: 102,
        ordinal: 14,
        scene_key: "S14",
        start_paragraph_id: "B0001-C0002-P0014",
        end_paragraph_id: "B0001-C0002-P0014",
        is_single_paragraph: true,
        boundary_source: "章末",
      },
      fields: {
        goal: { summary: "目标十四", evidence_paragraph_ids: ["B0001-C0002-P0014"] },
      },
      evidence: [
        {
          field_path: "goal.evidence",
          group: "goal",
          paragraph_id: "B0001-C0002-P0014",
          in_scope: true,
          order_index: 14,
        },
      ],
      illegal_evidence: [],
      analysis_artifact: {
        id: 202,
        analysis: {
          goal: { summary: "目标十四", evidence_paragraph_ids: ["B0001-C0002-P0014"] },
        },
      },
    },
  ],
};

afterEach(cleanup);

beforeEach(() => {
  vi.mocked(analysisApi.results).mockResolvedValue(scenePayload as any);
  vi.mocked(analysisApi.sceneParagraphs).mockImplementation(async (sceneId) => {
    const id = Number(sceneId);
    return {
      paragraphs: [
        {
          id: id === 102 ? "B0001-C0002-P0014" : "B0001-C0002-P0001",
          raw_text: id === 102 ? "第十四段。" : "第一段。",
          in_scene: true,
          paragraph_index: id === 102 ? 14 : 1,
        },
      ],
    } as any;
  });
  vi.mocked(analysisApi.createReaderJourney).mockReset();
});

function renderEmbedded(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/books/:bookId" element={<AnalysisResultRouteAdapter runId={55} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("embedded AnalysisResultsPage composition", () => {
  it("loads scene list and locates evidence without creating Reader Journey", async () => {
    renderEmbedded("/books/1?chapter=2&analysisRun=55&view=result");
    await waitFor(() => {
      expect(screen.getByTestId("scene-list")).toBeInTheDocument();
    });
    expect(screen.getByTestId("scene-list-item-1")).toBeInTheDocument();
    expect(screen.getByTestId("scene-list-item-14")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("scene-list-item-14"));
    await waitFor(() => {
      expect(analysisApi.sceneParagraphs).toHaveBeenCalledWith(102);
    });
    fireEvent.click(screen.getByTestId("tab-evidence"));
    const evidenceBtn = await screen.findByTestId("evidence-item-B0001-C0002-P0014");
    fireEvent.click(evidenceBtn);
    expect(document.getElementById("result-p-B0001-C0002-P0014")).toBeTruthy();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
    expect(screen.queryByTestId("journey-sync-workspace")).not.toBeInTheDocument();
  });

  it("does not show empty journey panel when journey is missing", async () => {
    renderEmbedded("/books/1?chapter=2&analysisRun=55&view=result");
    await waitFor(() => expect(screen.getByTestId("scene-list")).toBeInTheDocument());
    expect(screen.queryByTestId("journey-sync-workspace")).not.toBeInTheDocument();
    expect(analysisApi.createReaderJourney).not.toHaveBeenCalled();
  });
});
