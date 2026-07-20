import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";

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

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");

function renderJourney(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("Phase 1C-C.2.4A overview–detail layout", () => {
  const visualization = buildMockReaderJourneyVisualization();

  it("keeps overview fixed and detail in an independent pane", () => {
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
        activePhaseOrdinal={4}
      />,
    );

    expect(screen.getByTestId("journey-overview-pane")).toBeInTheDocument();
    expect(screen.getByTestId("journey-detail-pane")).toBeInTheDocument();
    expect(screen.getByTestId("journey-phase-strip")).toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-svg")).toBeInTheDocument();
    expect(screen.getByTestId("journey-active-scene-guide")).toBeInTheDocument();
    expect(screen.getByTestId("journey-detail-drawer")).toHaveTextContent("Scene 12");

    expect(css).toMatch(/journey-workspace-split/);
    expect(css).toMatch(/journey-resizable-split/);
    expect(css).toMatch(/\.journey-overview-pane[\s\S]*overflow:\s*hidden/);
    expect(css).toMatch(/\.journey-detail-pane[\s\S]*overflow:\s*auto/);
  });

  it("uses fixed-height compact phase cards without essay-length default copy", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    const card = screen.getByTestId("journey-phase-3");
    expect(card).toHaveTextContent(/转折|推进|入局|收束/);
    expect(card.textContent).not.toMatch(/平均牵引/);
    expect(card.textContent).not.toMatch(/核心问题/);
    expect(card.textContent).not.toMatch(/阶段回报/);
    expect(card.textContent).not.toMatch(/续读/);
    expect(css).toMatch(/\.journey-workspace-v4\s+\.journey-phase-nav-card[\s\S]*min-height:\s*96px/);
  });

  it("enlarges curve with Y ticks and S1–S14 X labels", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    const svg = screen.getByTestId("journey-curve-svg");
    expect(svg.getAttribute("height")).toBe("420");
    for (const tick of [100, 75, 50, 25, 0]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("journey-x-label-1")).toHaveTextContent("S1");
    expect(screen.getByTestId("journey-x-label-14")).toHaveTextContent("S14");
    expect(screen.getByTestId("journey-metric-select")).toHaveTextContent("阅读牵引");
  });

  it("marks active scene with guide and larger node without changing selection API", () => {
    const onSelectionChange = vi.fn();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
        onSelectionChange={onSelectionChange}
      />,
    );
    expect(screen.getByTestId("journey-active-scene-guide")).toBeInTheDocument();
    const node = screen.getByTestId("journey-curve-node-12");
    expect(node.getAttribute("class")).toContain("journey-node-active");
    fireEvent.click(screen.getByTestId("journey-curve-node-14"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 14, source: "journey_scene" }),
    );
  });

  it("shows marker legend and hook tier attributes", () => {
    renderJourney(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
    );
    expect(screen.getByTestId("journey-curve-legend")).toHaveTextContent("钩子");
    fireEvent.click(screen.getByTestId("journey-marker-full"));
    expect(screen.getByTestId("journey-curve-legend")).toHaveTextContent("次级节点");
    const endNode = screen.getByTestId("journey-curve-node-14");
    expect(endNode.getAttribute("data-hook-tier")).toBe("chapter");
  });
});

