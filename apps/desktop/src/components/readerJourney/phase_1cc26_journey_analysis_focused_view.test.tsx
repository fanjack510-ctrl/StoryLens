import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import {
  isLegacyOverviewMode,
  normalizeOverviewModeParam,
  parseOverviewMode,
} from "./overviewMode";
import { exportJourneyPng } from "./exportJourneyPng";
import { expectJourneyTitleVisible, expectRemovedHierarchyChrome, openExportMenu } from "./journeyTestHelpers";

vi.mock("./exportJourneyPng", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./exportJourneyPng")>();
  return {
    ...actual,
    exportJourneyPng: vi.fn().mockResolvedValue({
      filename: "StoryLens_第1章_旅程分析_v1.1.png",
    }),
  };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const visualization = buildMockReaderJourneyVisualization();

function renderAt(ui: ReactElement, initial: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initial]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderWorkspace(initial: string, extra?: { analysisRunId?: number; journeyRunId?: number }) {
  return renderAt(
    <ReaderJourneyWorkspace
      visualization={visualization}
      chapterTitle="第1章 戏鬼回家"
      onLocateEvidence={vi.fn()}
      activeSceneOrdinal={9}
      analysisRunId={extra?.analysisRunId ?? 55}
      journeyRunId={extra?.journeyRunId ?? 2}
    />,
    initial,
  );
}


describe("Phase 1C-C.2.6 journey analysis focused view", () => {
  it("shows 阅读旅程 export title and hides legacy top-level overview tabs", () => {
    renderWorkspace("/?overview=curve&scene=9&metric=engagement");
    expectJourneyTitleVisible();
    expectRemovedHierarchyChrome();
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
    expect(screen.queryByTestId("overview-mode-curve")).not.toBeInTheDocument();
    expect(screen.queryByTestId("overview-mode-questions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("overview-mode-diagnosis")).not.toBeInTheDocument();
    expect(screen.queryByText("曲线总览")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "问题簇" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "章节诊断" })).not.toBeInTheDocument();
  });

  it("accepts legacy overview=curve|questions|diagnosis and always shows journey analysis", async () => {
    for (const mode of ["curve", "questions", "diagnosis"] as const) {
      cleanup();
      renderWorkspace(
        `/?overview=${mode}&scene=9&paragraph=B0001-C0002-P0090&inspector=scene&metric=curiosity`,
      );
      expectJourneyTitleVisible();
      expect(screen.getByTestId("journey-overview-curve")).toBeInTheDocument();
      expect(screen.queryByTestId("journey-overview-questions")).not.toBeInTheDocument();
      expect(screen.queryByTestId("journey-overview-diagnosis")).not.toBeInTheDocument();
      await waitFor(() => {
        expect(parseOverviewMode(mode)).toBe("curve");
      });
    }
  });

  it("normalizes legacy overview URL without dropping scene/paragraph/inspector/metric", () => {
    const params = new URLSearchParams(
      "overview=questions&scene=9&paragraph=B0001-C0002-P0090&inspector=scene&metric=tension",
    );
    expect(isLegacyOverviewMode(params.get("overview"))).toBe(true);
    const next = normalizeOverviewModeParam(params);
    expect(next.get("overview")).toBe("curve");
    expect(next.get("scene")).toBe("9");
    expect(next.get("paragraph")).toBe("B0001-C0002-P0090");
    expect(next.get("inspector")).toBe("scene");
    expect(next.get("metric")).toBe("tension");
  });

  it("keeps phase strip without summary cards", () => {
    renderWorkspace("/?overview=curve&scene=9");
    expect(screen.queryByTestId("summary-card-traction")).not.toBeInTheDocument();
    expect(screen.queryByTestId("journey-summary-cards")).not.toBeInTheDocument();
    expect(screen.getByTestId("journey-phase-strip").querySelectorAll("button")).toHaveLength(4);
  });

  it("uses lens selector instead of legacy metric menu in unified topbar", async () => {
    renderWorkspace("/?overview=curve&scene=9&metric=engagement");
    expect(screen.getByTestId("journey-lens-composite")).toHaveAttribute("aria-current", "true");
    expect(screen.queryByTestId("journey-metric-more")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-lens-plot_progress"));
    await waitFor(() => {
      expect(screen.getByTestId("journey-lens-plot_progress")).toHaveAttribute("aria-current", "true");
    });
  });

  it("shows above-chart unified legend", () => {
    renderWorkspace("/?overview=curve&scene=9");
    const legend = screen.getByTestId("journey-unified-legend");
    expect(legend).toHaveAttribute("data-legend-placement", "above-chart");
    expect(screen.getByTestId("journey-minimal-legend")).toBeInTheDocument();
    expect(within(legend).getByText(/悬念欠账/)).toBeInTheDocument();
  });

  it("keeps Scene insight panel and Phase questions in Context Inspector", () => {
    renderWorkspace("/?overview=curve&scene=9&inspector=scene");
    expect(screen.getByTestId("scene-detail-insight-panel")).toBeInTheDocument();
    expect(screen.getByTestId("scene-dimension-insight-text")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("journey-phase-1"));
    expect(screen.getByTestId("phase-detail-tab-questions")).toHaveTextContent("钩子回收");
    // 阅读阻力 is gone: it named a formula field rather than anything a reader experiences.
    expect(screen.queryByTestId("phase-detail-tab-risks")).not.toBeInTheDocument();
  });

  it("exports PNG with 阅读旅程 title and without legacy tabs", async () => {
    renderWorkspace("/?overview=questions&scene=9");
    expect(screen.getByTestId("journey-export-title")).toHaveTextContent("阅读旅程");
    expect(screen.queryByTestId("journey-overview-mode-tabs")).not.toBeInTheDocument();
    fireEvent.click(openExportMenu());
    await waitFor(() => {
      expect(exportJourneyPng).toHaveBeenCalled();
    });
    const feedback = await screen.findByTestId("journey-export-feedback");
    expect(feedback.textContent).toMatch(/旅程分析|阅读旅程/);
  });

  it("keeps curve/rhythm first-click and phase-without-scene-change semantics", async () => {
    const onSelectionChange = vi.fn();
    renderAt(
      <ReaderJourneyWorkspace
        visualization={visualization}
        chapterTitle="第1章 戏鬼回家"
        onLocateEvidence={vi.fn()}
        activeSceneOrdinal={9}
        activePhaseOrdinal={3}
        onSelectionChange={onSelectionChange}
      />,
      "/?overview=curve&scene=9&inspector=scene",
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-10"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 10 }),
    );
    onSelectionChange.mockClear();
    fireEvent.click(screen.getByTestId("journey-rhythm-dot-11"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activeSceneOrdinal: 11 }),
    );
    onSelectionChange.mockClear();
    fireEvent.click(screen.getByTestId("journey-phase-1"));
    expect(onSelectionChange).toHaveBeenCalledWith(
      expect.objectContaining({ activePhaseOrdinal: 1 }),
    );
    const scenePatches = onSelectionChange.mock.calls.filter(
      (call) => call[0]?.activeSceneOrdinal != null && call[0]?.activePhaseOrdinal === 1,
    );
    expect(scenePatches.every((call) => call[0].activeSceneOrdinal === undefined || call[0].activeSceneOrdinal === 9 || call[0].source === "journey_phase")).toBe(true);
  });

  it("does not call models or create runs (presentation-only)", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    renderWorkspace("/?overview=diagnosis&scene=9");
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
