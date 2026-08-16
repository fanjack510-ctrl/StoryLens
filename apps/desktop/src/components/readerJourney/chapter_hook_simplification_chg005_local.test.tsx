import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { HookPayoffTimeline } from "./HookPayoffTimeline";
import {
  buildChapterHookSimplificationModel,
  buildReaderQuestionChangeTrail,
  deriveChapterHookNodeLabelV1,
  deriveChapterHookSummaryLine,
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
        payoffs: [
          {
            scene_ordinal: 3,
            type: "partial",
            summary: "部分揭晓",
            evidence_paragraph_ids: ["B0001-C0001-P0010"],
          },
        ],
        status: "partially_resolved",
        display_status: "partially_resolved",
        consistency_status: "consistent",
        conflicts: [],
        primary_relation: {
          grade: "probable",
          payoff_ref: {
            scene_ordinal: 3,
            type: "partial",
            evidence_paragraph_ids: ["B0001-C0001-P0010"],
          },
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

  it("summary_line uses natural-language verdict instead of stats dump", () => {
    const model = buildChapterHookSimplificationModel(vizWithLoops());
    expect(model.summary_line).not.toMatch(/本章提出 \d+ 个|章末牵引：/);
    expect(model.summary_line).toMatch(/围绕|回应|牵引|疑问/);
    expect(model.summary_line).not.toMatch(/未回收风险|必须回收/);
  });

  it("reader question cards include status, change trail, and role", () => {
    const model = buildChapterHookSimplificationModel(vizWithLoops());
    expect(model.reader_question_cards.length).toBeGreaterThan(0);
    expect(model.reader_question_cards.length).toBeLessThanOrEqual(3);
    for (const card of model.reader_question_cards) {
      expect(card.question).not.toMatch(/smoke-fake|hook_0|L\d+$/);
      expect(["新提出", "部分回应", "已回应", "继续保留"]).toContain(card.status);
      expect(card.change_trail).toMatch(/S\d{2} 提出/);
      expect(card.role.length).toBeGreaterThan(2);
    }
    const loops = getNarrativeLoops(vizWithLoops());
    const trail = buildReaderQuestionChangeTrail(loops[0], 6);
    expect(trail).toMatch(/S01 提出/);
    expect(trail).toMatch(/S03 回应/);
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

  it("renders CHG-011 layout: verdict, reader questions, compact trajectory", () => {
    const onSelect = vi.fn();
    render(
      <HookPayoffTimeline
        visualization={vizWithLoops()}
        selectedLoopId="L1"
        selectedSceneOrdinal={3}
        onSelectLoop={onSelect}
      />,
    );
    expect(screen.queryByTestId("hook-chapter-blurb")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-payoff-stats")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-ending-pull")).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-resolution-verdict").textContent).not.toMatch(
      /本章提出 \d+ 个/,
    );
    expect(screen.getByTestId("hook-chapter-reader-questions")).toBeInTheDocument();
    expect(screen.getAllByTestId("hook-chapter-question-card").length).toBeGreaterThan(0);
    expect(screen.getByTestId("hook-chapter-scene-label-1").textContent).toBe("提出疑问");
    // Scoped to the trajectory. The vitals row above it legitimately shows 「—」 when a
    // fixture carries no hook score: a missing number must read as missing, and this
    // assertion is about scene labels never degrading to a dash.
    expect(
      within(screen.getByTestId("hook-chapter-scene-row")).queryByText("—"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("hook-chapter-scene-insight")).toBeInTheDocument();
    expect(screen.getByTestId("journey-stage-bands")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("hook-chapter-scene-1"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("empty state shows title and note without cards or trajectory", () => {
    const empty = vizWithLoops();
    (empty as { narrative_loops: unknown[] }).narrative_loops = [];
    render(<HookPayoffTimeline visualization={empty} />);
    expect(screen.getByTestId("hook-resolution-verdict").textContent).toContain(
      "本章未形成明确的阅读悬念",
    );
    expect(screen.getByTestId("hook-resolution-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-reader-questions")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hook-chapter-scene-row")).not.toBeInTheDocument();
  });

  it("preserves stage band palette", () => {
    expect(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand).toBe("#E4F1E8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand).toBe("#F7EDD8");
    expect(JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand).toBe("#E7EDF6");
  });

  it("deriveChapterHookSummaryLine avoids stats dump for reliable mode", () => {
    const model = buildChapterHookSimplificationModel(vizWithLoops());
    const line = deriveChapterHookSummaryLine({
      chapter_hook_mode: "reliable",
      reader_question_cards: model.reader_question_cards,
      ending_pull: model.ending_pull,
    });
    expect(line).not.toMatch(/\d+ 个/);
  });
});
