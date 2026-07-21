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

function visibleJourneyTitles(): HTMLElement[] {
  return Array.from(document.querySelectorAll("h1, h2, h3")).filter((el) => {
    if (el.textContent?.trim() !== "阅读旅程") return false;
    if (el.classList.contains("journey-export-only-title")) return false;
    if (el.classList.contains("sr-only")) return false;
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    return true;
  }) as HTMLElement[];
}


function openExportMenu() {
  const more = screen.queryByTestId("journey-more-chart-settings");
  if (more && !screen.queryByTestId("journey-export-png")) {
    fireEvent.click(more);
  }
  return screen.getByTestId("journey-export-png");
}

describe("Phase 1C-C.2.6.1 header and insight density", () => {
  it("shows exactly one visible journey analysis title on the page", () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第1章 戏鬼回家"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
      "/?overview=curve&scene=9",
    );
    expect(screen.getByTestId("journey-analysis-title")).toHaveTextContent("阅读旅程");
    expect(screen.getByTestId("journey-analysis-subtitle")).toHaveTextContent("第1章 戏鬼回家");
    expect(screen.getByTestId("journey-export-title")).toHaveClass("journey-export-only-title");
    expect(css).toMatch(/\.journey-export-only-title\s*\{[^}]*display:\s*none/s);
    const visible = visibleJourneyTitles();
    expect(visible.length).toBe(1);
  });

  it("keeps four insight items in a compact strip", () => {
    renderAt(
      <ReaderJourneyWorkspace visualization={visualization} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    const strip = screen.getByTestId("journey-summary-cards");
    expect(strip).toHaveAttribute("data-insight-strip", "true");
    expect(within(strip).getByTestId("summary-card-traction")).toBeInTheDocument();
    expect(within(strip).getByTestId("summary-card-peak")).toBeInTheDocument();
    expect(within(strip).getByTestId("summary-card-weak")).toBeInTheDocument();
    expect(within(strip).getByTestId("summary-card-hook")).toBeInTheDocument();
    expect(css).toMatch(/\.journey-insight-strip[\s\S]*max-height:\s*56px/);
    expect(css).toMatch(/\.journey-insight-item[\s\S]*max-height:\s*56px/);
  });

  it("makes traction clickable when cluster id exists", () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        onSelectionChange={onSelectionChange}
      />,
      "/?overview=curve",
    );
    const traction = screen.getByTestId("summary-card-traction");
    expect(traction.tagName).toBe("BUTTON");
    fireEvent.click(traction);
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        selectedQuestionClusterId: "qcl-primary",
        source: "journey_cluster",
      }),
    );
  });

  it("renders static traction when no cluster id", () => {
    const noCluster = buildMockReaderJourneyVisualization();
    noCluster.visible_question_clusters = [];
    noCluster.question_clusters = [];
    renderAt(
      <ReaderJourneyWorkspace visualization={noCluster} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    const traction = screen.getByTestId("summary-card-traction");
    expect(traction.tagName).not.toBe("BUTTON");
    expect(traction.className).toContain("journey-insight-static");
  });

  it("peak click selects peak scene via existing selection path", () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
        onSelectionChange={onSelectionChange}
      />,
      "/?overview=curve&scene=9&inspector=scene",
    );
    fireEvent.click(screen.getByTestId("summary-card-peak"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({
        activeSceneOrdinal: visualization.chapter_summary.peaks.engagement_peak.scene_ordinal,
        source: "journey_scene",
      }),
    );
  });

  it("weak interval click selects engagement valley scene, not interval start", () => {
    const onSelectionChange = vi.fn();
    const valley = visualization.chapter_summary.peaks.engagement_valley.scene_ordinal;
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
        onSelectionChange={onSelectionChange}
      />,
      "/?overview=curve&scene=9",
    );
    expect(screen.getByTestId("summary-card-weak")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("summary-card-weak"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: valley, source: "journey_scene" }),
    );
  });

  it("hook click opens hook inspector when strongest_hook exists", async () => {
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
      />,
      "/?overview=curve&scene=9",
    );
    const hook = screen.getByTestId("summary-card-hook");
    expect(hook.tagName).toBe("BUTTON");
    fireEvent.click(hook);
    await waitFor(() => {
      expect(screen.getByTestId("journey-detail-pane")).toHaveAttribute("data-inspector", "hook");
    });
  });

  it("static hook when strongest_hook missing", () => {
    const noHook = buildMockReaderJourneyVisualization();
    noHook.chapter_summary.strongest_hook = null;
    renderAt(
      <ReaderJourneyWorkspace visualization={noHook} onLocateEvidence={vi.fn()} />,
      "/?overview=curve",
    );
    const hook = screen.getByTestId("summary-card-hook");
    expect(hook.tagName).not.toBe("BUTTON");
    expect(hook.className).toContain("journey-insight-static");
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
    expect(screen.getByTestId("journey-summary-cards")).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});

