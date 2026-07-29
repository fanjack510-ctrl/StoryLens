import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import {
  buildChapterHookSimplificationModel,
  deriveChapterHookNodeLabelV1,
  selectImportantChapterHooks,
} from "./chapterHookSimplification";
import { getNarrativeLoops } from "./narrativeLoopView";
import { getLensExplanation, HOOK_PAYOFF_LENS_LEGEND } from "./readerJourneyLensExplanation";
import { JOURNEY_STAGE_VISUAL_TOKENS } from "./journeyVisualTokens";

function vizWithLoops(): ReaderJourneyVisualization {
  return {
    visualization_version: "test",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "t",
      diagnosis: "d",
      primary_traction: "p",
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: 6,
        phase_count: 3,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 6,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 90 },
        engagement_valley: { scene_ordinal: 2, value: 10 },
        curiosity_peak: { scene_ordinal: 1, value: 80 },
        tension_peak: { scene_ordinal: 1, value: 70 },
        emotional_peak: { scene_ordinal: 1, value: 60 },
      },
    },
    scene_nodes: Array.from({ length: 6 }, (_, i) => ({
      scene_id: i + 1,
      scene_ordinal: i + 1,
      role: "core",
      scores: {},
    })),
    curve_series: {},
    phases: [
      {
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
        average_engagement: 50,
        summary: "",
      },
      {
        ordinal: 2,
        title: "发展",
        start_scene_ordinal: 3,
        end_scene_ordinal: 5,
        average_engagement: 60,
        summary: "",
      },
      {
        ordinal: 3,
        title: "收束",
        start_scene_ordinal: 6,
        end_scene_ordinal: 6,
        average_engagement: 55,
        summary: "",
      },
    ],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    narrative_loops: [
      {
        loop_id: "L1",
        question: "主角为什么会出现在这里？",
        open_from_scene: 1,
        hook: [{ scene_ordinal: 1, type: "new", summary: "现身疑问", strength: 80 }],
        developments: [{ scene_ordinal: 2, kind: "development" }],
        payoffs: [{ scene_ordinal: 3, type: "partial", summary: "部分揭晓" }],
        status: "partially_resolved",
        display_status: "partially_resolved",
        consistency_status: "consistent",
        conflicts: [],
        primary_relation: {
          grade: "probable",
          payoff_ref: { scene_ordinal: 3, type: "partial" },
        },
      },
      {
        loop_id: "L2",
        question: "门外的人是谁？",
        open_from_scene: 4,
        hook: [{ scene_ordinal: 4, type: "new", strength: 70 }],
        developments: [{ scene_ordinal: 5, kind: "development" }],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "consistent",
        conflicts: [],
      },
      {
        loop_id: "L3",
        question: "那封信里写了什么？",
        open_from_scene: 4,
        hook: [{ scene_ordinal: 4, type: "new", strength: 65 }],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "consistent",
        conflicts: [],
      },
    ],
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
}

afterEach(() => cleanup());

describe("CHG-20260729-005 chapter hook simplification", () => {
  it("keeps tab name 钩子回收 and updates page blurb semantics", () => {
    expect(getLensExplanation("hook_payoff").title).toBe("钩子回收");
    expect(getLensExplanation("hook_payoff").one_line_summary).toContain(
      "提出了哪些问题",
    );
    expect(getLensExplanation("hook_payoff").one_line_summary).not.toMatch(
      /未回收即|回收率/,
    );
    expect(HOOK_PAYOFF_LENS_LEGEND.map((i) => i.label)).toEqual([
      "提出疑问",
      "加深悬念",
      "给出回应",
      "留到下章",
    ]);
  });

  it("overview uses raised/answered/carried/chapter_pull without unresolved-as-failure", () => {
    const model = buildChapterHookSimplificationModel(vizWithLoops());
    expect(model.overview.raised).toBeGreaterThanOrEqual(1);
    expect(model.overview.answered).toBeGreaterThanOrEqual(1);
    expect(model.overview.carried).toBeGreaterThanOrEqual(1);
    expect(["明确", "较弱", "暂无", "无法判断"]).toContain(model.overview.chapter_pull);
    expect(model.summary_line).not.toMatch(/未回收风险|必须回收/);
  });

  it("selects at most 3 important reader questions without internal ids", () => {
    const loops = getNarrativeLoops(vizWithLoops());
    const important = selectImportantChapterHooks(loops, 6, 3);
    expect(important.length).toBeGreaterThan(0);
    expect(important.length).toBeLessThanOrEqual(3);
    for (const h of important) {
      expect(h.reader_question).not.toMatch(/smoke-fake|hook_0|L\d+$/);
      expect(h.reader_question.length).toBeGreaterThan(1);
    }
  });

  it("deriveChapterHookNodeLabelV1 uses ordinary four labels with priority", () => {
    const viz = vizWithLoops();
    const loops = getNarrativeLoops(viz);
    const top = selectImportantChapterHooks(loops, 6, 1)[0]?.loop_id;
    const s1 = deriveChapterHookNodeLabelV1({
      sceneOrdinal: 1,
      maxScene: 6,
      loops,
      topImportantLoopId: top,
    });
    expect(s1.short_label).toBe("提出疑问");
    const s2 = deriveChapterHookNodeLabelV1({
      sceneOrdinal: 2,
      maxScene: 6,
      loops,
      topImportantLoopId: top,
    });
    expect(s2.short_label).toBe("加深悬念");
    const s3 = deriveChapterHookNodeLabelV1({
      sceneOrdinal: 3,
      maxScene: 6,
      loops,
      topImportantLoopId: top,
    });
    expect(s3.short_label).toBe("给出回应");
    const s6 = deriveChapterHookNodeLabelV1({
      sceneOrdinal: 6,
      maxScene: 6,
      loops,
      topImportantLoopId: top,
    });
    expect(s6.short_label).toBe("留到下章");
  });

  it("renders simplified timeline without technical multi-lane table", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="L1"
        selectedSceneOrdinal={1}
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.getByTestId("hook-chapter-blurb").textContent).toContain("提出了哪些问题");
    expect(screen.getByTestId("hook-stat-raised").textContent).toMatch(/本章提出/);
    expect(screen.getByTestId("hook-stat-answered").textContent).toMatch(/本章回应/);
    expect(screen.getByTestId("hook-stat-carried").textContent).toMatch(/继续保留/);
    expect(screen.getByTestId("hook-stat-chapter-pull").textContent).toMatch(/章末牵引/);
    expect(screen.queryByTestId("hook-stat-established")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-resolution-table")).not.toBeInTheDocument();
    expect(screen.queryAllByTestId("hook-payoff-loop-row")).toHaveLength(0);
    expect(screen.getByTestId("hook-chapter-scene-label-1").textContent).toMatch(/提出疑问|加深悬念|给出回应|留到下章|—/);
    expect(screen.getByTestId("journey-stage-bands")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("hook-chapter-scene-1"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("does not mark carried hooks as failure in UI copy", () => {
    render(<HookPayoffTimeline visualization={vizWithLoops()} />);
    const stats = screen.getByTestId("hook-payoff-stats").textContent || "";
    expect(stats).not.toMatch(/未回收风险|失败/);
    expect(stats).toContain("继续保留");
  });

  it("empty state without scene bus when no loops", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-scene-row")).not.toBeInTheDocument();
  });

  it("preserves stage band palette", () => {
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand).toBe("#E4F1E8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand).toBe("#F7EDD8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand).toBe("#E7EDF6");
  });
});
