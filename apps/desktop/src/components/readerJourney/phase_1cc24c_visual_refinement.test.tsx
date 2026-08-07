import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { StructuredChapterTextPane } from "./StructuredChapterTextPane";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { roleLabelZh } from "./journeyUiLabels";
import type { SceneResultItem } from "../../types";
import type { JourneySelectionState } from "../../types/journeySelection";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_ReaderJourney_v1.1.png",
    }),
  };
});

afterEach(cleanup);

function renderJourney(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

const syncCss = readFileSync(resolve(__dirname, "./syncWorkspace.css"), "utf8");

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
      paragraph_count: ordinal === 14 ? 5 : 3,
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

describe("Phase 1C-C.2.4C visual refinement", () => {
  const visualization = buildMockReaderJourneyVisualization();

  it("dims non-selected scenes with readable opacities", () => {
    expect(syncCss).toMatch(/scene-same-phase[\s\S]*opacity:\s*0\.85/);
    expect(syncCss).toMatch(/scene-other-phase[\s\S]*opacity:\s*0\.7/);
    const scenes = Array.from({ length: 14 }, (_, i) => makeScene(i + 1));
    const paragraphs = Array.from({ length: 70 }, (_, i) => ({
      id: `B0001-C0002-P${String(i + 1).padStart(4, "0")}`,
      paragraph_index: i + 1,
      raw_text: `段落 ${i + 1}`,
    }));
    const selection: JourneySelectionState = {
      pageMode: "sync",
      activePhaseId: 4,
      activeSceneId: 12,
      activeSceneOrdinal: 12,
      activeParagraphId: null,
      activeEvidenceIds: [],
      selectionSource: "journey_scene",
      selectedMetric: "engagement",
      selectedQuestionClusterId: null,
      flashParagraphId: null,
    };
    render(
      <StructuredChapterTextPane
        chapterTitle="第1章"
        scenes={scenes}
        visualization={visualization}
        paragraphs={paragraphs}
        selection={selection}
        onSelectScene={vi.fn()}
        onSelectParagraph={vi.fn()}
        onScrollSpyScene={vi.fn()}
        isScrollSpySuppressed={() => false}
      />,
    );
    expect(screen.getByTestId("structured-scene-header-12").closest("section")).toHaveClass(
      "scene-active",
    );
    expect(screen.getByTestId("structured-scene-header-1").closest("section")).toHaveClass(
      "scene-other-phase",
    );
  });

  it("simplifies scene titles and localizes roles/markers", () => {
    expect(roleLabelZh("secondary")).toBe("过渡场景");
    const scenes = [makeScene(12)];
    const paragraphs = [
      {
        id: "B0001-C0002-P0060",
        paragraph_index: 60,
        raw_text: "十二",
      },
    ];
    const selection: JourneySelectionState = {
      pageMode: "sync",
      activePhaseId: null,
      activeSceneId: 12,
      activeSceneOrdinal: 12,
      activeParagraphId: null,
      activeEvidenceIds: [],
      selectionSource: "url",
      selectedMetric: "engagement",
      selectedQuestionClusterId: null,
      flashParagraphId: null,
    };
    render(
      <StructuredChapterTextPane
        chapterTitle="第1章"
        scenes={scenes}
        visualization={visualization}
        paragraphs={paragraphs}
        selection={selection}
        onSelectScene={vi.fn()}
        onSelectParagraph={vi.fn()}
        onScrollSpyScene={vi.fn()}
        isScrollSpySuppressed={() => false}
      />,
    );
    const header = screen.getByTestId("structured-scene-header-12");
    expect(header.textContent).toMatch(/核心场景|过渡场景|过渡/);
    expect(screen.getByTestId("structured-scene-stage-label-12")).toHaveTextContent(
      /开端|发展|收束|转折/,
    );
    expect(header.textContent).not.toMatch(/Phase\s|Scene\s|B0001-C0002-P0060/);
    const marker = header.querySelector(".badge-hook, .badge-payoff, .badge-risk");
    if (marker) {
      expect(marker.getAttribute("title")).toBeTruthy();
      expect(marker.textContent).toMatch(/悬念|回应|阅读阻力/);
    }
  });

  it("drops summary cards from the journey analysis view", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-expanded-diagnosis")).not.toBeInTheDocument();
  });

  it("keeps scene selection without marker mode toggles", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
      />,
    );
    expect(screen.queryByTestId("journey-marker-compact")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-layer-banner")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景12/);
  });
});
