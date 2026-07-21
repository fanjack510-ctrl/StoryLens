import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { exportJourneyPng } from "./exportJourneyPng";
import { buildSingleChapterTemplateFixtures } from "./mockSingleChapterJourneyTemplateFixtures";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_adaptive_phase.png",
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function visualizationWithPhases(
  sceneCount: number,
  phaseCount: number,
): ReaderJourneyVisualization {
  const fixtures = buildSingleChapterTemplateFixtures();
  const twoPhase = fixtures.find((f) => f.visualization.phases.length === 2);
  const source = (phaseCount === 2 && twoPhase ? twoPhase : fixtures[0]).visualization;
  if (phaseCount === 1) {
    const nodes = source.scene_nodes.slice(0, sceneCount).map((node) => ({
      ...node,
      phase_ordinal: 1,
    }));
    return {
      ...source,
      phases: [
        {
          ordinal: 1,
          title: "单一阶段",
          start_scene_ordinal: 1,
          end_scene_ordinal: sceneCount,
          primary_reader_question: "唯一主问题？",
          dominant_emotion: "紧张",
          reading_payoff: "信息",
          continuation_motivation: "续读",
          summary: "单 Phase 覆盖全章",
          confidence: 0.8,
          average_engagement: 55,
          core_scene_count: 1,
          beat_count: Math.max(0, sceneCount - 1),
          scene_span: sceneCount,
        },
      ],
      scene_nodes: nodes,
      chapter_summary: {
        ...source.chapter_summary,
        counts: {
          ...source.chapter_summary.counts,
          scene_count: sceneCount,
          phase_count: 1,
        },
      },
    };
  }
  return source;
}

describe("DEFECT-012 adaptive phase UI compatibility", () => {
  it("renders Reader Journey UI with 1 Phase", () => {
    const visualization = visualizationWithPhases(3, 1);
    expect(visualization.phases).toHaveLength(1);
    render(
      <MemoryRouter initialEntries={["/?overview=curve&phase=1&inspector=phase"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          chapterTitle="短章单阶段"
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(1);
    expect(screen.getByTestId("journey-export-root")).toBeInTheDocument();
  });

  it("renders Reader Journey UI with 2 Phases", () => {
    const visualization = visualizationWithPhases(6, 2);
    expect(visualization.phases.length).toBe(2);
    render(
      <MemoryRouter initialEntries={["/?overview=curve&phase=1&inspector=phase"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          chapterTitle="短章两阶段"
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(2);
  });

  it("PNG export path accepts 1–2 Phase visualizations", async () => {
    const one = visualizationWithPhases(3, 1);
    render(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={one}
          chapterTitle="导出单阶段"
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    fireEvent.click(screen.getByTestId("journey-export-png"));
    await vi.waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
    const two = visualizationWithPhases(6, 2);
    cleanup();
    render(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={two}
          chapterTitle="导出两阶段"
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("journey-more-chart-settings"));
    fireEvent.click(screen.getByTestId("journey-export-png"));
    await vi.waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
  });

  it("inspector URL recovery works with a single Phase", () => {
    const visualization = visualizationWithPhases(2, 1);
    render(
      <MemoryRouter initialEntries={["/?overview=curve&phase=1&inspector=phase"]}>
        <ReaderJourneyWorkspace
          visualization={visualization}
          chapterTitle="Inspector单阶段"
          onLocateEvidence={vi.fn()}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(1);
  });
});
