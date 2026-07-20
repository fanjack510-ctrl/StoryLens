import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("exposes five detail tabs and three core metrics on overview", () => {
    render(
      <JourneySceneDetailPanel node={node1} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("scene-detail-tabs").querySelectorAll("button")).toHaveLength(5);
    expect(screen.getByTestId("scene-detail-score-bars")).toBeInTheDocument();
    expect(screen.getByTestId("score-bar-engagement")).toHaveTextContent("阅读牵引");
    expect(screen.getByTestId("score-bar-curiosity")).toBeInTheDocument();
    expect(screen.getByTestId("score-bar-tension")).toBeInTheDocument();
    expect(screen.queryByTestId("score-bar-dropoff_risk")).not.toBeInTheDocument();
  });

  it("localizes lifecycle labels and keeps tab across Scene switch", () => {
    expect(lifecycleLabelZh("created_here")).toBe("本场新增");
    expect(lifecycleLabelZh("transformed")).toBe("问题升级");
    const { rerender } = renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={1}
      />,
    );
    fireEvent.click(screen.getByTestId("scene-detail-tab-questions"));
    expect(screen.getByTestId("scene-detail-questions")).toHaveTextContent("本场景建立的问题");
    expect(screen.getByTestId("scene-detail-questions")).toHaveTextContent("留给后续的问题");
    rerender(
      <MemoryRouter>
        <ReaderJourneyWorkspace
          visualization={visualization}
          onLocateEvidence={vi.fn()}
          activeSceneOrdinal={8}
        />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("scene-detail-panel-questions")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("场景 08");
  });

  it("renders hook fields and writing takeaways without crashing", () => {
    render(
      <JourneySceneDetailPanel node={node14} onLocateEvidence={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("scene-detail-tab-payoffs"));
    expect(screen.getByTestId("primary-hook-grid")).toHaveTextContent("缺口");
    expect(screen.getByTestId("primary-hook-grid")).toHaveTextContent("继续动力");
    fireEvent.click(screen.getByTestId("scene-detail-tab-techniques"));
    expect(screen.getByTestId("journey-writing-takeaways")).toBeInTheDocument();
  });

  it("locates evidence from evidence tab for Scene 1 and Scene 14", () => {
    const onLocate = vi.fn();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={onLocate}
        activeSceneOrdinal={1}
      />,
    );
    const drawer = screen.getByTestId("journey-detail-drawer");
    fireEvent.click(within(drawer).getByTestId("scene-detail-tab-evidence"));
    fireEvent.click(within(drawer).getByTestId("journey-evidence-B0001-C0002-P0010"));
    expect(onLocate).toHaveBeenCalledWith("B0001-C0002-P0010");
  });

  it("shows empty states when fields are missing", () => {
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
    };
    render(<JourneySceneDetailPanel node={emptyNode} onLocateEvidence={vi.fn()} />);
    fireEvent.click(screen.getByTestId("scene-detail-tab-questions"));
    expect(screen.getByTestId("empty-questions")).toHaveTextContent("未识别出明确问题链");
    fireEvent.click(screen.getByTestId("scene-detail-tab-payoffs"));
    expect(screen.getByTestId("empty-hook-payoff")).toHaveTextContent("未识别出明确的钩子或回报");
    fireEvent.click(screen.getByTestId("scene-detail-tab-techniques"));
    expect(screen.getByTestId("empty-techniques")).toHaveTextContent("未提取出可复用技法");
    fireEvent.click(screen.getByTestId("scene-detail-tab-evidence"));
    expect(screen.getByTestId("empty-evidence")).toHaveTextContent("暂无可用证据");
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
