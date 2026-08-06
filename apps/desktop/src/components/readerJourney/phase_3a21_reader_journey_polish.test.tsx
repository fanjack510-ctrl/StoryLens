import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import { buildMockReaderJourneyVisualization } from "./mockVisualization";
import { resolvePhaseSummaryDisplay } from "./journeyUiLabels";
import { resolveJourneyLayoutMode } from "./journeyVisualizationConfig";
import { hasUsableJourneyVisualization } from "./hasUsableJourneyVisualization";
import { ReaderJourneyProgressCard } from "../chapterAnalysis/ReaderJourneyProgressCard";

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function mockViewportWidth(width: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(HTMLElement.prototype, "getBoundingClientRect", {
    configurable: true,
    value() {
      return {
        width,
        height: 900,
        top: 0,
        left: 0,
        bottom: 900,
        right: width,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      };
    },
  });
}

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
    expect(resolvePhaseSummaryDisplay("...", "入局")).toContain("阅读期待");
    expect(resolvePhaseSummaryDisplay("…", "推进")).toContain("核心冲突");
    expect(resolvePhaseSummaryDisplay("   ", "转折")).toContain("信息变化");
    expect(resolvePhaseSummaryDisplay("本章推进核心冲突", "推进")).toBe("本章推进核心冲突");
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
          status: "scene_profiles_running",
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
    expect(ordinary).toContain("正在分析场景特征");
    expect(ordinary).not.toMatch(/0\s*\/\s*0/);
    expect(ordinary).not.toMatch(/AnalysisRun|JourneyRun|scene_profiles_running|\brunning\b/);
    expect(screen.getByTestId("reader-journey-progress-stage")).toHaveTextContent("正在分析场景特征");
    expect(screen.getByTestId("reader-journey-progress-tech")).toHaveTextContent("scene_profiles_running");
  });

  it("detail inspector uses a single collapse control and Chinese scene title", () => {
    mockViewportWidth(1440);
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
    expect(screen.getByTestId("scene-detail-title").textContent).toMatch(/场景04/);
    expect(screen.queryByTestId("journey-inspector-close")).toBeNull();
    expect(screen.getAllByTestId("journey-collapse-inspector").length).toBe(1);
    expect(screen.getByTestId("journey-collapse-inspector")).toHaveTextContent("收起详情");
    const detailText = screen.getByTestId("journey-detail-pane").textContent || "";
    expect(detailText).not.toMatch(/\bPhase\b|所属 Phase|相关Scene|Scene 4 summary|Scene 4 写作启示/);
    expect(detailText).toMatch(/场景04|进一步推进|控制信息密度/);
  });

  it("phase cards never render a lone period or ellipsis description", () => {
    mockViewportWidth(1440);
    const viz = buildMockReaderJourneyVisualization();
    viz.phases = viz.phases.map((p, i) => {
      if (i === 0) return { ...p, summary: "." };
      if (i === 1) return { ...p, summary: "..." };
      if (i === 2) return { ...p, summary: "…" };
      return { ...p, summary: "   " };
    });
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
      const text = (desc?.textContent || "").trim();
      expect(text).not.toBe(".");
      expect(text).not.toBe("...");
      expect(text).not.toBe("…");
      expect(text.length).toBeGreaterThan(1);
      expect(text).not.toMatch(/^[\.\s…]+$/);
      expect(text).toMatch(/(阅读期待|核心冲突|信息变化|后续期待|进入|信息铺垫|推进|收束|冲突|推动|中段|阶段|抬升|形成)/);
    }
  });

  it("1024 narrow detail closed has expand entry without orphan collapse", () => {
    mockViewportWidth(1024);
    const viz = buildMockReaderJourneyVisualization();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={viz}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
    );
    expect(screen.getByTestId("journey-workspace")).toHaveAttribute("data-layout", "narrow");
    expect(screen.queryByTestId("journey-collapse-inspector")).toBeNull();
    expect(screen.getByTestId("journey-inspector-summary-expand")).toHaveTextContent("展开详情");
    fireEvent.click(screen.getByTestId("journey-tab-inspector"));
    expect(screen.getByTestId("journey-inspector-pane")).toBeVisible();
    expect(screen.getAllByTestId("journey-collapse-inspector")).toHaveLength(1);
    expect(screen.getByTestId("journey-collapse-inspector")).toHaveTextContent("收起详情");
    fireEvent.click(screen.getByTestId("journey-collapse-inspector"));
    expect(screen.queryByTestId("journey-collapse-inspector")).toBeNull();
    expect(screen.getByTestId("journey-inspector-summary-expand")).toBeInTheDocument();
  });

  it("empty selection hints are Chinese without Phase/Scene jargon", () => {
    mockViewportWidth(1440);
    const viz = buildMockReaderJourneyVisualization();
    renderJourney(
      <ReaderJourneyWorkspace
        visualization={viz}
        chapterTitle="第一章"
        onLocateEvidence={vi.fn()}
        compactHead
      />,
    );
    fireEvent.click(screen.getByTestId("journey-inspector-summary-expand"));
    const empty = screen.getByTestId("journey-detail-empty");
    expect(empty).toHaveTextContent("选择一个阶段、场景或曲线节点");
    expect(empty.textContent).not.toMatch(/\bPhase\b|\bScene\b|\bHook\b/);
  });
});
