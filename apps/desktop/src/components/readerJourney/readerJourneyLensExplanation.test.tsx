import { describe, expect, it } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import {
  READER_JOURNEY_LENS_EXPLANATIONS,
  getLensExplanation,
  isTautologyContinueDrive,
  lensIdFromMetric,
  metricForLens,
  parseLensParam,
  shortPlainTitle,
} from "./readerJourneyLensExplanation";
import { JourneyLensExplanationChrome } from "./JourneyLensExplanationChrome";
import {
  buildHookPayoffChapterStats,
  buildHookPayoffTimelineModel,
} from "./hookPayoffTimelineModel";
import type { NarrativeLoopView } from "./narrativeLoopView";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { afterEach } from "vitest";

afterEach(() => cleanup());

describe("readerJourneyLensExplanation", () => {
  it("provides one-line summary and at most three how-to-read items for every lens", () => {
    for (const lens of Object.keys(READER_JOURNEY_LENS_EXPLANATIONS) as Array<
      keyof typeof READER_JOURNEY_LENS_EXPLANATIONS
    >) {
      const explanation = getLensExplanation(lens);
      expect(explanation.one_line_summary.length).toBeGreaterThan(8);
      expect(explanation.one_line_summary.length).toBeLessThanOrEqual(80);
      expect(explanation.how_to_read).toHaveLength(3);
      for (const item of explanation.how_to_read) {
        expect(item.length).toBeLessThanOrEqual(40);
      }
    }
  });

  it("maps lens <-> metric for URL sync and rejects illegal lens", () => {
    expect(metricForLens("hook_payoff")).toBe("hook");
    expect(lensIdFromMetric("hook")).toBe("hook_payoff");
    expect(lensIdFromMetric("arousal")).toBe("emotion");
    expect(parseLensParam("hook_payoff")).toBe("hook_payoff");
    expect(parseLensParam("nope")).toBeNull();
  });

  it("filters tautology continue-drive and short titles", () => {
    expect(isTautologyContinueDrive("继续阅读")).toBe(true);
    expect(isTautologyContinueDrive("想知道门外是谁")).toBe(false);
    expect(shortPlainTitle("这是一个很长很长的问题标题需要截断吗？？", 10)).toMatch(/…$/);
    expect(shortPlainTitle("短问？")).toBe("短问？");
  });
});

describe("JourneyLensExplanationChrome", () => {
  it("renders one-liner, how-to panel with max three items, and minimal legend", () => {
    render(<JourneyLensExplanationChrome lensId="composite" />);
    expect(screen.getByTestId("journey-lens-one-liner").textContent).toContain("不代表一定写得差");
    expect(screen.getByTestId("journey-lens-title").textContent).toBe("综合阅读动力");
    fireEvent.click(screen.getByTestId("journey-lens-how-to-trigger"));
    const panel = screen.getByTestId("journey-lens-how-to-panel");
    expect(panel.querySelectorAll("li")).toHaveLength(3);
    expect(screen.getByTestId("journey-minimal-legend").textContent).toContain("场景");
  });

  it("keeps optional legacy chrome stats when explicitly passed", () => {
    render(
      <JourneyLensExplanationChrome
        lensId="hook_payoff"
        hookPayoffStats={{ established: 3, answered: 1, waiting: 2, delayed_risk: 1 }}
        inconsistentWarning="当前关系识别存在严重冲突，暂不作为确定结论。"
      />,
    );
    expect(screen.getByTestId("journey-lens-title").textContent).toMatch(/钩子/);
    expect(screen.getByTestId("journey-hook-payoff-stats")).toBeInTheDocument();
    expect(screen.getByTestId("journey-loop-inconsistent-banner").textContent).toContain(
      "严重冲突",
    );
  });
});

describe("hookPayoffTimelineModel", () => {
  const loops: NarrativeLoopView[] = [
    {
      loop_id: "L1",
      scope: {},
      question: "门外是谁",
      information_gap: "门外身份",
      hook: [{ scene_ordinal: 1, summary: "门外有人" }],
      developments: [{ scene_ordinal: 2 }],
      payoffs: [
        {
          scene_ordinal: 3,
          type: "full",
          summary: "是邻居",
          evidence_paragraph_ids: ["p3"],
        },
      ],
      residual_question: "",
      status: "resolved",
      evidence: ["p3"],
      confidence: 0.8,
      consistency_status: "consistent",
      conflicts: [],
      open_from_scene: 1,
      nodes_spanned: 3,
    },
    {
      loop_id: "L2",
      scope: {},
      question: "第二张脸是谁",
      information_gap: "",
      hook: [{ scene_ordinal: 4, summary: "镜中异象" }],
      developments: [{ scene_ordinal: 5 }],
      payoffs: [],
      residual_question: "第二张脸是谁",
      status: "open",
      evidence: [],
      confidence: 0.7,
      consistency_status: "consistent",
      conflicts: [],
      open_from_scene: 4,
      nodes_spanned: 2,
      has_partial_response: false,
    },
  ];

  it("computes chapter stats and builds links by loop_id only", () => {
    const stats = buildHookPayoffChapterStats(loops);
    expect(stats.established).toBe(2);
    expect(stats.answered).toBe(1);
    expect(stats.waiting).toBe(1);
    expect(stats.delayed_risk).toBe(1);

    const viz = {
      scene_nodes: [{ scene_ordinal: 1 }, { scene_ordinal: 5 }],
      narrative_loops: loops,
      narrative_loop_consistency: { status: "consistent", conflict_count: 0, conflicts: [] },
    } as unknown as ReaderJourneyVisualization;
    const model = buildHookPayoffTimelineModel(viz, { selectedLoopId: "L1" });
    expect(model.links.every((link) => link.loop_id === "L1" || link.loop_id === "L2")).toBe(true);
    expect(model.links.some((link) => link.from_id.includes("L1") && link.to_id.includes("L1"))).toBe(
      true,
    );
    expect(model.nodes.some((n) => n.kind === "open" && n.loop_id === "L2")).toBe(true);
    expect(model.nodes.filter((n) => n.loop_id === "L2" && n.rail === "payoff")).toHaveLength(0);
  });

  it("draws graded primary link on soft conflict; hard block draws none", () => {
    const softViz = {
      scene_nodes: [{ scene_ordinal: 1 }, { scene_ordinal: 3 }],
      narrative_loops: [
        {
          ...loops[0],
          consistency_status: "soft_conflict",
          soft_conflict: true,
          hard_blocked: false,
          status: "resolved",
          display_status: "resolved",
          conflicts: [{ code: "payoff_score_without_entity", message: "x" }],
          primary_relation: {
            loop_id: "L1",
            grade: "probable",
            total_score: 72,
            is_primary: true,
            payoff_ref: { scene_ordinal: 3, type: "full", summary: "钥匙找到了" },
          },
        },
      ],
      narrative_loop_consistency: {
        status: "soft_conflict",
        conflict_count: 1,
        conflicts: [],
        user_message: "系统找到较可信的承接，但部分分析结果仍存在分歧。",
      },
    } as unknown as ReaderJourneyVisualization;
    const softModel = buildHookPayoffTimelineModel(softViz);
    expect(softModel.inconsistent).toBe(false);
    expect(softModel.softConflict).toBe(true);
    expect(softModel.links).toHaveLength(1);
    expect(softModel.links[0].grade).toBe("probable");
    expect(softModel.links[0].stroke).toBe("dashed");
    expect(softModel.warning).toContain("分歧");

    const hardViz = {
      scene_nodes: [{ scene_ordinal: 1 }, { scene_ordinal: 3 }],
      narrative_loops: [
        {
          ...loops[0],
          consistency_status: "inconsistent",
          hard_blocked: true,
          status: "inconsistent",
          conflicts: [{ code: "fingerprint_mismatch", message: "fp" }],
          primary_relation: {
            loop_id: "L1",
            grade: "unsupported",
            total_score: 0,
            blocked: true,
            is_primary: true,
          },
        },
      ],
      narrative_loop_consistency: {
        status: "inconsistent",
        conflict_count: 1,
        conflicts: [],
        user_message: "当前关系识别存在严重冲突，暂不作为确定结论。",
      },
    } as unknown as ReaderJourneyVisualization;
    const hardModel = buildHookPayoffTimelineModel(hardViz);
    expect(hardModel.inconsistent).toBe(true);
    expect(hardModel.links).toHaveLength(0);
    expect(hardModel.warning).toContain("严重冲突");
  });
});
