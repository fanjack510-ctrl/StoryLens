import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { JourneyDetailErrorBoundary } from "./JourneyDetailErrorBoundary";
import {
  JourneyMarkerInspectorPanel,
  JourneyPhaseDetailPanel,
  JourneyQuestionInspectorPanel,
  JourneySceneDetailPanel,
} from "./JourneySceneDetailPanel";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { JourneyInspectorEmptyState, JourneyEvidenceList } from "./inspectorShell";

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

beforeEach(() => {
  localStorage.clear();
});

function renderJourney(ui: ReactElement) {
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width: 1600,
        height: 900,
        top: 0,
        left: 0,
        bottom: 900,
        right: 1600,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      };
    },
  });
  return render(
    <MemoryRouter>
      <div style={{ width: 1600 }}>{ui}</div>
    </MemoryRouter>,
  );
}

describe("Phase 1C-C.2.7 Context Inspector hierarchy", () => {
  const visualization = buildMockReaderJourneyVisualization();
  const node1 = visualization.scene_nodes[0];
  const node8 = visualization.scene_nodes[7];
  const node9 = visualization.scene_nodes[8];
  const phase3 = visualization.phases[2];
  const cluster = visualization.visible_question_clusters?.[0] ?? visualization.question_clusters?.[0];

  it("renders unified Scene Inspector header with at most 2 pills", () => {
    render(<JourneySceneDetailPanel node={node9} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("journey-inspector-header")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent(/场景09/);
    const pills = screen.queryAllByTestId("journey-inspector-pill");
    expect(pills.length).toBeLessThanOrEqual(2);
  });

  it("renders unified Phase Inspector header", () => {
    render(
      <JourneyPhaseDetailPanel
        phase={phase3}
        visualization={visualization}
        onSelectScene={vi.fn()}
      />,
    );
    expect(screen.getByTestId("journey-inspector-header")).toBeInTheDocument();
    expect(screen.getByTestId("phase-detail-title")).toHaveTextContent(/转折|阶段/);
  });

  it("renders unified Question Inspector header", () => {
    expect(cluster).toBeTruthy();
    render(
      <JourneyQuestionInspectorPanel
        cluster={cluster!}
        nodes={visualization.scene_nodes}
        onSelectScene={vi.fn()}
      />,
    );
    expect(screen.getByTestId("journey-question-inspector")).toBeInTheDocument();
    expect(screen.getByTestId("journey-inspector-header")).toBeInTheDocument();
  });

  it("renders unified Hook/Payoff Inspector headers", () => {
    const hookNode = visualization.scene_nodes.find((n) => n.primary_hook) ?? node1;
    render(
      <JourneyMarkerInspectorPanel kind="hook" node={hookNode} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("journey-hook-inspector")).toBeInTheDocument();
    cleanup();
    const payoffNode = visualization.scene_nodes.find((n) => n.primary_payoff) ?? node1;
    render(<JourneyMarkerInspectorPanel kind="payoff" node={payoffNode} />);
    expect(screen.getByTestId("journey-payoff-inspector")).toBeInTheDocument();
    // The risk inspector is gone with 阅读阻力 itself: it reported a derived field name and
    // its penalty arithmetic, which describes the formula rather than the reader. Nothing
    // could reach it once the chart's risk markers were removed, so it went too.
  });

  it("prioritizes Scene dimension insight and Phase one-line conclusions", () => {
    render(<JourneySceneDetailPanel node={node9} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
    cleanup();
    render(
      <JourneyPhaseDetailPanel
        phase={phase3}
        visualization={visualization}
        onSelectScene={vi.fn()}
      />,
    );
    expect(screen.getByTestId("phase-primary-conclusion")).toHaveTextContent(phase3.summary);
  });

  it("omits empty risk section on simplified Scene panel", () => {
    const noRisk = {
      ...node1,
      primary_risk: null,
      risk_points: [],
    };
    render(<JourneySceneDetailPanel node={noRisk} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("scene-overview-risk")).not.toBeInTheDocument();
  });

  it("shows unavailable insight copy on simplified Scene panel when data missing", () => {
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
      primary_risk: null,
      dimension_insights: { overall_reading: null },
    };
    render(<JourneySceneDetailPanel node={emptyNode} onLocateEvidence={vi.fn()} />);
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toHaveTextContent(
      "当前维度暂无可靠洞察",
    );
    expect(screen.queryByTestId("scene-detail-tab-questions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("empty-techniques")).not.toBeInTheDocument();
  });

  it("keeps empty state height constrained", () => {
    const css = readFileSync(join(__dirname, "readerJourney.css"), "utf8");
    expect(css).toMatch(/\.journey-inspector-empty-state[\s\S]*?max-height:\s*96px/);
  });

  it("does not create runs from empty state actions", () => {
    const createRun = vi.fn();
    render(
      <JourneyInspectorEmptyState
        kind="no-question-chain"
        testId="empty-action"
        actionLabel="查看概览"
        onAction={() => undefined}
      />,
    );
    fireEvent.click(screen.getByText("查看概览"));
    expect(createRun).not.toHaveBeenCalled();
  });

  it("distinguishes Error Boundary from empty state", () => {
    function Boom(): null {
      throw new Error("render boom");
    }
    render(
      <JourneyDetailErrorBoundary>
        <Boom />
      </JourneyDetailErrorBoundary>,
    );
    expect(screen.getByTestId("journey-detail-error")).toBeInTheDocument();
    expect(screen.queryByTestId("empty-questions")).not.toBeInTheDocument();
  });

  it("renders writing_takeaways variants without crashing simplified Scene panel", () => {
    const cases = [
      { writing_takeaways: "单句启示" as unknown },
      { writing_takeaways: ["启示A", "启示B"] as unknown },
      { writing_takeaways: { summary: "对象启示" } as unknown },
      {
        writing_takeaways: [
          { summary: "对象A", applicable_when: "开篇" },
          { summary: "对象B" },
        ] as unknown,
      },
    ];
    for (const patch of cases) {
      const node = { ...node1, ...(patch as object), techniques: [] };
      const { unmount } = render(
        <JourneySceneDetailPanel node={node as typeof node1} onLocateEvidence={vi.fn()} />,
      );
      expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
      expect(screen.queryByTestId("journey-detail-error")).not.toBeInTheDocument();
      unmount();
    }
  });

  it("shows at most 5 evidence rows by default and expands", () => {
    const rows = Array.from({ length: 7 }, (_, i) => ({
      paragraphId: `P${i}`,
      conclusion: `c${i}`,
      kind: "scene",
    }));
    const onLocate = vi.fn();
    render(<JourneyEvidenceList rows={rows} onLocateEvidence={onLocate} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(5);
    fireEvent.click(screen.getByTestId("journey-evidence-expand"));
    expect(screen.getAllByRole("listitem")).toHaveLength(7);
    fireEvent.click(screen.getByTestId("journey-evidence-P6"));
    expect(onLocate).toHaveBeenCalledWith("P6");
  });

  it("uses compact related Scene list and preserves click", () => {
    const onSelect = vi.fn();
    render(
      <JourneyPhaseDetailPanel
        phase={phase3}
        visualization={visualization}
        onSelectScene={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("phase-detail-tab-scenes"));
    expect(screen.getByTestId("phase-related-scenes")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("phase-related-scene-9"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("declares a single inspector scroll region marker", () => {
    render(<JourneySceneDetailPanel node={node9} onLocateEvidence={vi.fn()} />);
    expect(screen.getAllByTestId("journey-inspector-body")).toHaveLength(1);
    expect(screen.getByTestId("journey-inspector-body")).toHaveAttribute(
      "data-scroll-region",
      "inspector",
    );
  });

  it("shows actionable no-selection empty state without auto-selecting Scene", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    // Inspector is collapsed by default (curve-first); expand to reach empty state.
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    const empty = screen.getByTestId("journey-detail-empty");
    expect(empty).toHaveTextContent("选择一个阶段");
    expect(empty).toHaveTextContent("点击曲线节点查看场景变化");
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "empty");
  });

  it("Phase click keeps Scene and does not call model", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
      />,
    );
    fireEvent.click(screen.getByTestId("journey-phase-3"));
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "phase");
    expect(screen.getByTestId("journey-rhythm-dot-9")).toHaveClass("selected");
  });

  it("CSS keeps inspector body without nested overflow auto on shell", () => {
    const css = readFileSync(join(__dirname, "readerJourney.css"), "utf8");
    expect(css).toMatch(
      /\.journey-workspace-split \.journey-detail-drawer\.journey-inspector-shell[\s\S]*?overflow:\s*visible/,
    );
  });
});
