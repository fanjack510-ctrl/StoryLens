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

    expect(screen.getByTestId("journey-analysis-title")).toHaveTextContent("旅程分析");
    expect(screen.getByTestId("journey-summary-cards")).toBeInTheDocument();
    expect(screen.getByTestId("summary-card-traction")).toBeInTheDocument();
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

    fireEvent.click(screen.getByTestId("journey-metric-select"));
    fireEvent.click(screen.getByTestId("journey-metric-hook"));
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("钩子");

    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    expect(screen.getByTestId("journey-detail-drawer")).toHaveTextContent("Scene 14");
    expect(screen.getByTestId("scene-detail-tab-questions")).toHaveTextContent("问题链");

    expect(screen.getByTestId("journey-export-png")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
  });

  it("defaults to compact marker mode and analysis info popover", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("journey-marker-compact").className).toContain("active");
    expect(screen.getByTestId("journey-marker-compact")).toHaveTextContent("精简标记");
    expect(screen.queryByTestId("journey-layer-banner")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-analysis-info"));
    expect(screen.getByTestId("journey-analysis-info-popover")).toHaveTextContent(
      /visualization v1\.1/,
    );
  });

  it("toggles full marker mode", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("journey-marker-full"));
    expect(screen.getByTestId("journey-marker-full").className).toContain("active");
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
    expect(screen.getByTestId("scene-detail-tab-questions")).toHaveTextContent("问题链");
  });

  it("shows compact chapter summary cards", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("summary-card-traction")).toHaveTextContent("核心牵引");
    expect(screen.getByTestId("summary-card-peak")).toHaveTextContent("峰值");
    expect(screen.getByTestId("summary-card-weak")).toHaveTextContent("薄弱区间");
    expect(screen.getByTestId("summary-card-hook")).toHaveTextContent("章尾钩子");
  });

  it("shows diagnosis summary on the single journey analysis view", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=diagnosis",
    );
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-expanded-diagnosis")).not.toBeInTheDocument();
    expect(screen.getByTestId("summary-card-traction")).toBeInTheDocument();
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
});
