import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { exportJourneyPng } from "./exportJourneyPng";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_旅程分析_v1.1.png",
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const visualization = buildMockReaderJourneyVisualization();

function renderAt(ui: ReactElement, initial: string) {
  return render(<MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>);
}


function openExportMenu() {
  const more = screen.queryByTestId("journey-more-chart-settings");
  if (more && !screen.queryByTestId("journey-export-png")) {
    fireEvent.click(more);
  }
  return screen.getByTestId("journey-export-png");
}

describe("Phase 1C-C.2.6.2 compact phase navigation strip", () => {
  it("shows Phase 1-4 with two primary rows each", () => {
    renderAt(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=curve&scene=9",
    );
    for (const n of [1, 2, 3, 4]) {
      const card = screen.getByTestId(`journey-phase-${n}`);
      expect(card.querySelectorAll(".journey-phase-card-head")).toHaveLength(1);
      expect(card.querySelectorAll(".journey-phase-card-desc")).toHaveLength(1);
      expect(card.querySelector(".journey-phase-question")).toBeNull();
      expect(card.querySelector(".journey-phase-payoff")).toBeNull();
    }
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(4);
  });

  it("uses ellipsis title truncation with full title attribute", () => {
    const longTitle = "意识觉醒与身份迷雾以及超长阶段标题用于验证省略号截断效果";
    const longViz = {
      ...visualization,
      phases: visualization.phases.map((phase) =>
        phase.ordinal === 1 ? { ...phase, title: longTitle } : phase,
      ),
    };
    renderAt(
      <ReaderJourneyWorkspace visualization={longViz} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    const card = screen.getByTestId("journey-phase-1");
    const title = card.querySelector(".journey-phase-title");
    expect(title).toHaveTextContent(longTitle);
    expect(card.getAttribute("title") || "").toContain(longTitle);
    expect(css).toMatch(
      /\.journey-phase-card\.journey-phase-nav-card\s+\.journey-phase-title[\s\S]*?text-overflow:\s*ellipsis/,
    );
    expect(css).toMatch(
      /\.journey-phase-card\.journey-phase-nav-card\s+\.journey-phase-title[\s\S]*?white-space:\s*nowrap/,
    );
    expect(css).not.toMatch(/-webkit-line-clamp:\s*2;\s*\n\s*-webkit-box-orient:\s*vertical;\s*\n\s*white-space:\s*normal/);
  });

  it("shows scene range and labeled metric score", () => {
    renderAt(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    const card = screen.getByTestId("journey-phase-2");
    expect(card).toHaveTextContent(/推进/);
    expect(within(card).getByTestId("journey-phase-avg-2").textContent).toMatch(/阅读动力\s+\d+/);
    expect(card.textContent).not.toMatch(/平均牵引/);
    expect(card.textContent).not.toMatch(/核心问题/);
    expect(card.textContent).not.toMatch(/阶段回报/);
    expect(card.textContent).not.toMatch(/继续动力/);
    expect(card.textContent).not.toMatch(/æ|å|ç|è|ï¿½|�/);
  });

  it("marks current phase without a current badge", () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        activePhaseOrdinal={3}
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&phase=3&inspector=phase",
    );
    const card = screen.getByTestId("journey-phase-3");
    expect(card).toHaveClass("active-phase");
    expect(card).toHaveAttribute("aria-selected", "true");
    expect(within(card).queryByTestId("journey-phase-current-badge")).not.toBeInTheDocument();
    expect(card.querySelectorAll(".journey-phase-card-head")).toHaveLength(1);
    expect(card.querySelectorAll(".journey-phase-card-desc")).toHaveLength(1);
    expect(within(card).getByTestId("journey-phase-avg-3").textContent).toMatch(/阅读动力/);
    expect(within(card).getByTestId("journey-phase-avg-3").textContent).not.toMatch(/当前/);
  });

  it("keeps equal compact card height and desktop four columns in CSS", () => {
    expect(css).toMatch(/\.journey-workspace-v4\s+\.journey-phase-nav-card[\s\S]*min-height:\s*96px/);
    expect(css).toMatch(/\.journey-workspace-v4\s+\.journey-phase-nav-card[\s\S]*max-height:\s*none/);
    expect(css).toMatch(
      /\.journey-phase-strip\.journey-phase-nav[\s\S]*grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)/,
    );
  });

  it("defines mid-width two-column phase cards and narrow dropdown layouts", () => {
    expect(css).toMatch(/@media\s*\(max-width:\s*1100px\)\s*and\s*\(min-width:\s*701px\)/);
    expect(css).toMatch(/grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
    expect(css).toMatch(/@media\s*\(max-width:\s*700px\)/);
    expect(css).toMatch(/\.journey-phase-mobile-select-wrap[\s\S]*display:\s*flex/);
    expect(css).toMatch(
      /\.journey-workspace\.journey-exporting\s+\.journey-phase-strip\.journey-phase-nav[\s\S]*grid-template-columns:\s*repeat\(4/,
    );
  });

  it("reuses phase click semantics: no scene/paragraph change; inspector=phase", () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        activeSceneOrdinal={9}
        activePhaseOrdinal={2}
        onSelectionChange={onSelectionChange}
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&scene=9&paragraph=B0001-C0002-P0090&phase=2",
    );
    fireEvent.click(screen.getByTestId("journey-phase-4"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        activePhaseOrdinal: 4,
        source: "journey_phase",
      }),
    );
    const sceneCalls = onSelectionChange.mock.calls.filter(
      (call) => call[0]?.activeSceneOrdinal != null || call[0]?.sceneOrdinal != null,
    );
    expect(sceneCalls).toHaveLength(0);
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "phase");
    expect(screen.getByTestId("journey-phase-detail-panel")).toBeInTheDocument();
  });

  it("mobile select reuses the same phase handler", () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        activeSceneOrdinal={9}
        onSelectionChange={onSelectionChange}
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&scene=9",
    );
    const select = screen.getByTestId("journey-phase-mobile-select");
    fireEvent.change(select, { target: { value: "4" } });
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activePhaseOrdinal: 4, source: "journey_phase" }),
    );
    expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "phase");
  });

  it("keeps standard curve height 420 and a single active scene marker", () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        activeSceneOrdinal={9}
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&scene=9",
    );
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    expect(screen.getAllByTestId("journey-active-scene-guide")).toHaveLength(1);
  });

  it("PNG export path still invokes exporter once without model/runs", async () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        analysisRunId={55}
        journeyRunId={2}
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&scene=9",
    );
    fireEvent.click(openExportMenu());
    await waitFor(() => {
      expect(exportJourneyPng).toHaveBeenCalledTimes(1);
    });
    expect(css).toMatch(
      /\.journey-workspace\.journey-exporting\s+\.journey-phase-mobile-select-wrap[\s\S]*display:\s*none/,
    );
  });

  it("does not clip titles via two-line clamp inside fixed 72px shell", () => {
    expect(css).not.toMatch(/min-height:\s*72px;\s*max-height:\s*72px/);
    expect(css).toMatch(/\.journey-workspace-v4\s+\.journey-phase-nav-card[\s\S]*min-height:\s*96px/);
  });
});

