import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { parseOverviewMode } from "./overviewMode";

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

const css = readFileSync(resolve(__dirname, "./readerJourney.css"), "utf8");
const visualization = buildMockReaderJourneyVisualization();

function renderWorkspace(initial = "/?overview=curve&scene=12") {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
        activePhaseOrdinal={4}
      />
    </MemoryRouter>,
  );
}

describe("Phase 1C-C.2.5A overview modes (superseded by 2.6 single view)", () => {
  it("maps all overview values to the single journey analysis curve view", () => {
    expect(parseOverviewMode(null)).toBe("curve");
    expect(parseOverviewMode("questions")).toBe("curve");
    expect(parseOverviewMode("diagnosis")).toBe("curve");
    renderWorkspace("/?scene=12");

    expect(screen.getByTestId("journey-analysis-title")).toHaveTextContent("旅程分析");
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overview-questions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-overview-diagnosis")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-curve-svg")).toBeInTheDocument();
    expect(screen.getByTestId("journey-active-scene-guide")).toBeInTheDocument();
    expect(screen.getByTestId("scene-detail-title")).toHaveTextContent("Scene 12");
  });

  it("uses compact two-line phase nav without essay copy and standard curve height 408", () => {
    renderWorkspace();
    const card = screen.getByTestId("journey-phase-3");
    expect(card).toHaveTextContent(/Phase 3 · S/);
    expect(card.querySelector(".journey-phase-row1")).toBeTruthy();
    expect(card.querySelector(".journey-phase-row2")).toBeTruthy();
    expect(card.textContent).not.toMatch(/平均牵引/);
    expect(card.textContent).not.toMatch(/核心问题/);
    expect(card.textContent).not.toMatch(/阶段回报/);
    expect(css).toMatch(/\.journey-phase-card\.journey-phase-compact[\s\S]*height:\s*64px/);
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    for (const tick of [100, 75, 50, 25, 0]) {
      expect(screen.getByTestId(`journey-y-tick-${tick}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("journey-x-label-1")).toHaveTextContent("S1");
    expect(screen.getByTestId("journey-x-label-14")).toHaveTextContent("S14");
  });

  it("keeps question-cluster CSS helpers without mounting top-level questions overview", () => {
    renderWorkspace("/?overview=questions");
    expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
    expect(screen.queryByTestId("journey-question-chains")).not.toBeInTheDocument();
    expect(css).toMatch(
      /\.journey-overview-questions\s+\.journey-cluster-members\s*\{[\s\S]*?position:\s*static/,
    );
  });
});

