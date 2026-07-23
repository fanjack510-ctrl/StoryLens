import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import type { ReactElement } from "react";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_旅程分析_v1.1.png",
    }),
  };
});

afterEach(cleanup);

function renderJourney(ui: ReactElement, initial = "/") {
  return render(<MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>);
}

describe("ReaderJourneyWorkspace", () => {
  const visualization = buildMockReaderJourneyVisualization();

  it("renders diagnosis, phases, curve nodes, drawer, metrics, and export", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第1章 戏鬼回家"
        onLocateEvidence={vi.fn()}
        onSelectScene={vi.fn()}
      />,
    );

    expect(screen.getByTestId("journey-export-title")).toHaveTextContent("阅读旅程");
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-marker-toggle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-chapter-summary-bullets")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-curve-legend")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-unified-legend")).toBeInTheDocument();
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(4);

    for (let ordinal = 1; ordinal <= 14; ordinal += 1) {
      expect(screen.getByTestId(`journey-curve-node-${ordinal}`)).toBeInTheDocument();
    }

    const coreNode = screen.getByTestId("journey-curve-node-1");
    const beatNode = screen.getByTestId("journey-curve-node-3");
    expect(coreNode.getAttribute("class")).toContain("journey-node-core");
    expect(beatNode.getAttribute("class")).toContain("journey-node-beat");
    expect(coreNode.querySelector("circle")?.getAttribute("r")).not.toBe(
      beatNode.querySelector("circle")?.getAttribute("r"),
    );

    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    expect(screen.getByTestId("journey-detail-drawer")).toHaveTextContent("场景14");
    expect(screen.getByTestId("scene-detail-tab-questions")).toHaveTextContent(/问题|为什么/);

    expect(screen.getByTestId("journey-overlay-composite")).toHaveTextContent("对比分析");
    expect(screen.queryByTestId("journey-more-chart-settings")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-hook"));
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("钩子");
    expect(screen.queryByTestId("journey-overlay-composite")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
  });

  it("does not expose 更多操作 or analysis info in ordinary topbar", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.queryByTestId("journey-marker-compact")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-marker-full")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-analysis-info-popover")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-more-chart-settings")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-analysis-info")).not.toBeInTheDocument();
  });

  it("does not expose full marker mode controls", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.queryByTestId("journey-marker-full")).not.toBeInTheDocument();
  });

  it("keeps question chains available in Scene Inspector (legacy overview questions removed)", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={1}
      />,
      "/?overview=questions&scene=1&inspector=scene",
    );
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-cluster-toggle-qcl-primary")).not.toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-tab-questions")).toHaveTextContent(/问题|为什么/);
  });

  it("does not render bottom chapter summary cards", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.queryByTestId("summary-card-traction")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
  });

  it("keeps curve workspace when overview=diagnosis alias is used", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=diagnosis",
    );
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-expanded-diagnosis")).not.toBeInTheDocument();
    expect(screen.queryByTestId("summary-card-traction")).not.toBeInTheDocument();
  });

  it("calls onLocateEvidence from drawer evidence buttons", () => {
    const onLocateEvidence = vi.fn();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={onLocateEvidence}
      />,
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-1"));
    const drawer = screen.getByTestId("journey-detail-drawer");
    fireEvent.click(within(drawer).getByTestId("scene-detail-tab-evidence"));
    fireEvent.click(within(drawer).getByTestId("journey-evidence-B0001-C0002-P0010"));
    expect(onLocateEvidence).toHaveBeenCalledWith("B0001-C0002-P0010");
  });

  it("calls onSelectionChange when curve node clicked in controlled mode", () => {
    const onSelectionChange = vi.fn();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={null}
        activePhaseOrdinal={null}
        selectedMetric="engagement"
        onSelectionChange={onSelectionChange}
      />,
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 14, source: "journey_scene" }),
    );
  });

  it("highlights active scene with journey-node-active", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={14}
        selectedMetric="engagement"
      />,
    );
    expect(screen.getByTestId("journey-curve-node-14").getAttribute("class")).toContain(
      "journey-node-active",
    );
  });

  it("shows full phase cards and keeps phase ids on select", () => {
    const onSelectionChange = vi.fn();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activePhaseOrdinal={null}
        onSelectionChange={onSelectionChange}
      />,
    );
    const phase1 = screen.getByTestId("journey-phase-1");
    expect(phase1).toHaveTextContent(/入局|推进|转折|收束/);
    expect(screen.getByTestId("journey-phase-avg-1").textContent).not.toMatch(/undefined|NaN/);
    fireEvent.click(phase1);
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activePhaseOrdinal: 1, source: "journey_phase" }),
    );
  });

  it("expands and collapses detail without clearing selection", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={4}
        activePhaseOrdinal={2}
      />,
      "/?scene=4&inspector=scene",
    );
    expect(screen.getByTestId("journey-detail-pane")).toBeInTheDocument();
    const collapse = screen.getAllByTestId("journey-collapse-inspector")[0];
    fireEvent.click(collapse!);
    expect(screen.getByTestId("journey-inspector-summary-expand")).toBeInTheDocument();
    expect(screen.getByTestId("journey-inspector-summary-text").textContent).toMatch(/场景\s*04/);
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    expect(screen.getByTestId("journey-detail-pane")).toBeInTheDocument();
  });

  it("keeps metric value identity when switching metrics", () => {
    const onSelectionChange = vi.fn();
    const before = visualization.curve_series.engagement?.[0]?.value;
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        selectedMetric="engagement"
        onSelectionChange={onSelectionChange}
      />,
    );
    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-tension"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ selectedMetric: "tension" }),
    );
    expect(visualization.curve_series.engagement?.[0]?.value).toBe(before);
  });
});
