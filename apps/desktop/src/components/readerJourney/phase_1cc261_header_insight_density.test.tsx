import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { exportJourneyPng } from "./exportJourneyPng";
import { expectRemovedHierarchyChrome, openExportMenu } from "./journeyTestHelpers";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_Chapter_ReaderJourney_v1.1.png",
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

describe("Phase 1C-C.2.6.1 header and insight density", () => {
  it("uses export-only journey title after header simplification", () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第1章 戏鬼回家"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
      "/?overview=curve&scene=9",
    );
    expectRemovedHierarchyChrome();
    expect(screen.getByTestId("journey-analysis-header")).toHaveAttribute("hidden");
    expect(screen.getByTestId("journey-export-title")).toHaveTextContent("阅读旅程");
    expect(screen.getByTestId("journey-export-title")).toHaveClass("journey-export-only-title");
    expect(css).toMatch(/\.journey-export-only-title\s*\{[^}]*display:\s*none/s);
  });

  it("drops the four-card insight strip from ordinary chrome", () => {
    renderAt(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.queryByTestId("summary-card-traction")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button").length).toBeGreaterThan(0);
  });

  it("phase click does not change scene via insight path regression", () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
        activePhaseOrdinal={3}
        onSelectionChange={onSelectionChange}
      />,
      "/?overview=curve&scene=9",
    );
    fireEvent.click(screen.getByTestId("journey-phase-1"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activePhaseOrdinal: 1, source: "journey_phase" }),
    );
    expect(onSelectionChange).not.toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: expect.anything(), source: "journey_phase" }),
    );
  });

  it("keeps a single active scene marker and responsive curve height", () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={12}
      />,
      "/?overview=curve&scene=12",
    );
    expect(screen.getAllByTestId("journey-active-scene-guide")).toHaveLength(1);
    expect(screen.getByTestId("journey-curve-svg").getAttribute("height")).toBe("420");
    expect(screen.getByTestId("journey-curve-container")).toBeInTheDocument();
    expect(css).toMatch(/\.journey-overview-curve \.journey-curve-svg[\s\S]*width:\s*100%/);
  });

  it("PNG export uses single export title and does not call models", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第1章 戏鬼回家"
        onLocateEvidence={vi.fn()}
      />,
      "/?overview=curve&scene=9",
    );
    fireEvent.click(openExportMenu());
    await waitFor(() => expect(exportJourneyPng).toHaveBeenCalled());
    expect(screen.getByTestId("journey-export-title")).toHaveTextContent("阅读旅程");
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
