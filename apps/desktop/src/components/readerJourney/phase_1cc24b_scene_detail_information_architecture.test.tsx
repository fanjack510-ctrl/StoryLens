import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { JourneyDetailErrorBoundary } from "./JourneyDetailErrorBoundary";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { lifecycleLabelZh } from "./journeyUiLabels";

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

describe("Phase 1C-C.2.4B Scene detail information architecture", () => {
  const visualization = buildMockReaderJourneyVisualization();
  const node1 = visualization.scene_nodes[0];
  const node14 = visualization.scene_nodes[13];

  it("uses simplified Scene Inspector without legacy tabs", () => {
    render(
      <JourneySceneDetailPanel node={node1} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.queryByTestId("scene-detail-tabs")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-detail-score-bars")).not.toBeInTheDocument();
  });

  it("localizes lifecycle labels and keeps title across Scene switch", () => {
    expect(lifecycleLabelZh("created_here")).toBe("本场新增");
    expect(lifecycleLabelZh("transformed")).toBe("问题升级");
    const { rerender } = renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={1}
      />,
    );
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景01/);
    rerender(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={8}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景08/);
  });

  it("renders Scene 14 insight panel without crashing", () => {
    render(
      <JourneySceneDetailPanel node={node14} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-detail-error")).not.toBeInTheDocument();
  });

  it("shows unavailable insight copy when fields are missing", () => {
    const emptyNode = {
      ...node1,
      reader_question_in: [],
      reader_question_created: [],
      reader_question_answered: [],
      reader_question_out: [],
      payoffs: [],
      hooks: [],
      primary_hook: null,
      primary_payoff: null,
      techniques: [],
      writing_takeaways: [],
      evidence_paragraph_ids: [],
      risk_points: [],
      dimension_insights: { overall_reading: null },
    };
    render(<JourneySceneDetailPanel node={emptyNode} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toHaveTextContent(
      "当前维度暂无可靠洞察",
    );
    expect(screen.queryByTestId("empty-questions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("empty-evidence")).not.toBeInTheDocument();
  });

  it("keeps Error Boundary isolation", () => {
    function Boom(): null {
      throw new Error("detail boom");
    }
    render(
      <JourneyDetailErrorBoundary>
        <Boom />
      </JourneyDetailErrorBoundary>,
    );
    expect(screen.getByTestId("journey-detail-error")).toBeInTheDocument();
  });
});
