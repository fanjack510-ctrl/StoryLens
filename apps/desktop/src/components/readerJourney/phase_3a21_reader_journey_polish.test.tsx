import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { resolvePhaseSummaryDisplay } from "./journeyUiLabels";
import { resolveJourneyLayoutMode } from "./journeyVisualizationConfig";
import { hasUsableJourneyVisualization } from "./hasUsableJourneyVisualization";
import { ReaderJourneyProgressCard } from "../chapterAnalysis/ReaderJourneyProgressCard";

afterEach(cleanup);

function renderJourney(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("Reader Journey 3A.2.1 polish", () => {
  it("layout breakpoints follow viewport thresholds", () => {
    expect(resolveJourneyLayoutMode(1440)).toBe("desktop");
    expect(resolveJourneyLayoutMode(1300)).toBe("mid");
    expect(resolveJourneyLayoutMode(1180)).toBe("mid");
    expect(resolveJourneyLayoutMode(1179)).toBe("narrow");
    expect(resolveJourneyLayoutMode(1024)).toBe("narrow");
  });

  it("phase summary '.' uses structural Chinese fallback", () => {
    expect(resolvePhaseSummaryDisplay(".", "收束")).toContain("后续期待");
    expect(resolvePhaseSummaryDisplay(".", "收束")).not.toBe(".");
  });

  it("empty visualization is not usable", () => {
    const viz = buildMockReaderJourneyVisualization();
    expect(
      hasUsableJourneyVisualization({
        status: "succeeded",
        visualization: {
          ...viz,
          scene_nodes: [],
          phases: [],
          curve_series: { ...viz.curve_series, engagement: [] },
        },
      }),
    ).toBe(false);
  });

  it("loading card never shows 0/0 or AnalysisRun in ordinary copy", () => {
    render(
      <ReaderJourneyProgressCard
        analysisRunId={55}
        progress={{
          journey_run_id: 701,
          analysis_run_id: 55,
          status: "running",
          total_scene_count: 0,
          completed_scene_count: 0,
          remaining_scene_count: 0,
          phase_count: 0,
          has_chapter_summary: false,
          retryable: true,
        } as any}
        onViewTaskDetails={() => undefined}
      />,
    );
    const card = screen.getByTestId("reader-journey-progress-card");
    const ordinary = card.textContent?.replace(/技术详情[\s\S]*$/, "") || "";
    expect(ordinary).toContain("正在生成阅读旅程");
    expect(ordinary).toContain("正在处理场景数据");
    expect(ordinary).not.toMatch(/0\s*\/\s*0/);
    expect(ordinary).not.toMatch(/AnalysisRun|JourneyRun|\brunning\b/);
    expect(screen.getByTestId("reader-journey-progress-stage")).toHaveTextContent("生成中");
  });

  it("detail inspector uses a single collapse control and Chinese scene title", () => {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    const viz = buildMockReaderJourneyVisualization();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={viz}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
    );
    fireEvent.click(screen.getByTestId("journey-curve-node-4"));
    expect(screen.getByTestId("scene-detail-title").textContent).toMatch(/场景 04/);
    expect(screen.queryByTestId("journey-inspector-close")).toBeNull();
    expect(screen.getAllByTestId("journey-collapse-inspector").length).toBeGreaterThanOrEqual(1);
    const detailText = screen.getByTestId("journey-detail-pane").textContent || "";
    expect(detailText).not.toMatch(/\bPhase\b|所属 Phase|相关Scene/);
  });

  it("phase cards never render a lone period description", () => {
    const viz = buildMockReaderJourneyVisualization();
    viz.phases = viz.phases.map((p, i) =>
      i === 0 ? { ...p, summary: "." } : { ...p, summary: "   " },
    );
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={viz}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
    );
    for (const ordinal of [1, 2, 3, 4]) {
      const card = screen.getByTestId(`journey-phase-${ordinal}`);
      const desc = card.querySelector(".journey-phase-card-desc");
      expect(desc?.textContent?.trim()).not.toBe(".");
      expect((desc?.textContent || "").trim().length).toBeGreaterThan(1);
    }
  });

  it("empty selection hints are Chinese without Phase/Scene jargon", () => {
    const viz = buildMockReaderJourneyVisualization();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={viz}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
    );
    const empty = screen.getByTestId("journey-detail-empty");
    expect(empty).toHaveTextContent("选择一个阶段、场景或曲线节点");
    expect(empty.textContent).not.toMatch(/\bPhase\b|\bScene\b|\bHook\b/);
  });
});
