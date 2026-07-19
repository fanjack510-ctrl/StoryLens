import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { StructuredChapterTextPane } from "./StructuredChapterTextPane";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import type { SceneResultItem } from "../../types";
import type { JourneySelectionState } from "../../types/journeySelection";

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

const selection: JourneySelectionState = {
  pageMode: "sync",
  activePhaseId: null,
  activeSceneId: 14,
  activeSceneOrdinal: 14,
  activeParagraphId: "B0001-C0002-P0064",
  activeEvidenceIds: ["B0001-C0002-P0064"],
  selectionSource: "journey_scene",
  selectedMetric: "engagement",
  selectedQuestionClusterId: null,
  flashParagraphId: null,
};

describe("StructuredChapterTextPane", () => {
  const visualization = buildMockReaderJourneyVisualization();
  const scenes = Array.from({ length: 14 }, (_, i) => makeScene(i + 1));
  const paragraphs = Array.from({ length: 70 }, (_, i) => ({
    id: `B0001-C0002-P${String(i + 1).padStart(4, "0")}`,
    paragraph_index: i + 1,
    raw_text: `段落 ${i + 1}`,
  }));

  it("renders data attributes and active scene highlight", () => {
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

    const scene14 = screen.getByTestId("structured-scene-header-14").closest("section");
    expect(scene14).toHaveClass("scene-active");
    expect(scene14).toHaveAttribute("data-scene-ordinal", "14");
    expect(scene14).toHaveAttribute("data-start-paragraph-id", "B0001-C0002-P0064");
    expect(scene14).toHaveAttribute("data-end-paragraph-id", "B0001-C0002-P0068");

    const paragraph = screen.getByTestId("sync-paragraph-B0001-C0002-P0064");
    expect(paragraph).toHaveAttribute("data-paragraph-id", "B0001-C0002-P0064");
    expect(paragraph).toHaveAttribute("data-scene-ordinal", "14");
    expect(paragraph).toHaveClass("evidence-mark");
  });

  it("calls onSelectScene when scene header clicked", () => {
    const onSelectScene = vi.fn();
    render(
      <StructuredChapterTextPane
        chapterTitle="第1章"
        scenes={scenes}
        visualization={visualization}
        paragraphs={paragraphs}
        selection={{ ...selection, activeSceneOrdinal: null, activeSceneId: null }}
        onSelectScene={onSelectScene}
        onSelectParagraph={vi.fn()}
        onScrollSpyScene={vi.fn()}
        isScrollSpySuppressed={() => false}
      />,
    );
    fireEvent.click(screen.getByTestId("structured-scene-header-9"));
    expect(onSelectScene).toHaveBeenCalledWith(9);
  });

  it("programmatic scrollToParagraph uses instant behavior", () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
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
      expect(scrollIntoView).toHaveBeenCalled();
      expect(scrollIntoView.mock.calls[0]?.[0]).toEqual(
        expect.objectContaining({ behavior: "auto", block: "center" }),
      );
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });
});
