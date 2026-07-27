/**
 * Hook/payoff lens semantics — local Vitest (CHG-20260721-012).
 * Presentation/binding only; no weight retuning.
 */
import { describe, expect, it } from "vitest";
import { buildLensChartLines, mainCurveSeries, equalWeightMainCurveSeries } from "./observationLenses";
import { buildLinePathD, resolveMetricValue } from "./journeyChartScales";
import { buildSegmentMarkers } from "./journeySegmentMarkers";
import {
  HOOK_STRENGTH_LABEL,
  PAYOFF_NOT_CUMULATIVE_HINT,
  PAYOFF_STRENGTH_LABEL,
  buildHookPayoffChapterBullets,
  buildHookPayoffSceneSummary,
  formatHookPayoffSceneCaption,
  getQuestionLifecycle,
  hookPayoffCombinationExplanation,
  payoffPlainLanguage,
  phaseHookPayoffAverages,
  primaryBandLabelForHookPayoffLens,
  questionsForScene,
} from "./hookPayoffLensModel";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";

function minimalViz(nodes: Partial<JourneySceneNode>[]): ReaderJourneyVisualization {
  const scene_nodes = nodes.map((partial, index) => {
    const ordinal = partial.scene_ordinal ?? index + 1;
    const baseScores = {
      curiosity: 50,
      tension: 50,
      payoff: 40,
      hook: 55,
      information_gain: 45,
      emotional_resonance: 40,
      cognitive_load: 30,
      dropoff_risk: 35,
      valence_start: -20,
      valence_end: 10,
      arousal_start: 40,
      arousal_end: 60,
      ...(partial.scores ?? {}),
    } as JourneySceneNode["scores"];
    return {
      scene_id: ordinal,
      scene_ordinal: ordinal,
      paragraph_range: {
        start_paragraph_id: `P${ordinal}`,
        end_paragraph_id: `P${ordinal}`,
      },
      paragraph_count: 5,
      phase_ordinal: 1,
      role: partial.role ?? "core",
      importance_score: 50,
      importance_formula_version: "1.0",
      deterministic_reasons: [],
      scene_value_summary: partial.scene_value_summary ?? `场景 ${ordinal}`,
      dominant_emotion: "紧张",
      engagement: { engagement_score: 60 },
      scores: baseScores,
      reader_question_in: [],
      reader_question_created: [],
      reader_question_answered: [],
      reader_question_out: [],
      payoffs: [],
      hooks: [],
      techniques: [],
      risk_points: [],
      character_effects: [],
      writing_takeaways: [],
      evidence_paragraph_ids: [],
      evidence_count: 0,
      confidence: partial.confidence ?? 0.8,
      primary_payoff: null,
      primary_hook: null,
      primary_risk: null,
      node_type: partial.node_type,
      include_in_main_curve: partial.include_in_main_curve,
      primary_diagnosis: partial.primary_diagnosis,
      secondary_diagnoses: partial.secondary_diagnoses,
      positive_mechanism: partial.positive_mechanism,
    } as JourneySceneNode;
  });

  const emptySeries = scene_nodes.map((n) => ({
    scene_ordinal: n.scene_ordinal,
    value: 50,
  }));

  return {
    visualization_version: "1.1",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "测试章",
      diagnosis: "",
      primary_traction: "",
      primary_cluster_title: "",
      core_scene_count: scene_nodes.length,
      strong_hook_count: 0,
      stage_payoff_count: 0,
      max_low_payoff_interval: null,
      max_fragmentation_interval: null,
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: scene_nodes.length,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: scene_nodes.length,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 60 },
        engagement_valley: { scene_ordinal: 1, value: 40 },
        engagement_average: 50,
      },
      expanded_diagnosis: {},
    },
    phases: [
      {
        ordinal: 1,
        title: "开端",
        summary: "测试阶段",
        start_scene_ordinal: 1,
        end_scene_ordinal: scene_nodes.length,
        average_engagement: 50,
      },
    ],
    curve_series: {
      engagement: emptySeries,
      curiosity: emptySeries,
      tension: emptySeries,
      payoff: emptySeries,
      hook: emptySeries,
      dropoff_risk: emptySeries,
      valence: emptySeries.map((p) => ({ ...p, start: -10, end: 10 })),
      arousal: emptySeries.map((p) => ({ ...p, start: 40, end: 60 })),
    },
    scene_nodes,
    role_counts: { core: scene_nodes.length, secondary: 0, beat: 0 },
    primary_question_chain: null,
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [],
    risk_intervals: [],
    formula_versions: {
      visualization_version: "1.1",
      chain_rank_formula_version: "1.0",
      importance_formula_version: "1.0",
      chain_merge_formula_version: "1.0",
      hook_select_formula_version: "1.0",
      payoff_derive_formula_version: "1.0",
      cluster_formula_version: "1.0",
      engagement_formula_version: "2.0",
    },
    calibration_status: {
      source_mode: "v2_native",
      scene_contract_version: "2.0",
      calibrated: true,
    },
    question_lifecycle: [],
  } as unknown as ReaderJourneyVisualization;
}

describe("hook/payoff line field binding", () => {
  it("green solid reads scores.hook; purple dashed reads scores.payoff (本场)", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 80, payoff: 20 } as never },
      { scene_ordinal: 2, scores: { hook: 45, payoff: 70 } as never },
    ]);
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(lines[0].labelZh).toBe("钩子强度");
    expect(lines[0].style).toBe("solid");
    expect(lines[1].labelZh).toBe("回报强度");
    expect(lines[1].style).toBe("dashed");
    expect(lines[0].series.map((p) => resolveMetricValue(p))).toEqual([80, 45]);
    expect(lines[1].series.map((p) => resolveMetricValue(p))).toEqual([20, 70]);
  });

  it("does not carry-forward missing payoff or hook", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 65, payoff: 65 } as never },
      { scene_ordinal: 2, scores: { hook: 50, payoff: 40 } as never },
      { scene_ordinal: 3, scores: { hook: 40, payoff: 30 } as never },
    ]);
    delete (viz.scene_nodes[1].scores as Record<string, unknown>).payoff;
    delete (viz.scene_nodes[2].scores as Record<string, unknown>).hook;
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(lines[1].series.map((p) => resolveMetricValue(p))).toEqual([65, null, 30]);
    expect(lines[0].series.map((p) => resolveMetricValue(p))).toEqual([65, 50, null]);
    const payoffPath = buildLinePathD(
      lines[1].series,
      (o) => o * 10,
      (v) => 100 - v,
    );
    // Missing middle point must break the path (two subpaths), not invent a plateau.
    expect(payoffPath.split("M ").length - 1).toBeGreaterThanOrEqual(2);
  });

  it("explicit payoff=0 draws as 0, not missing", () => {
    const viz = minimalViz([{ scene_ordinal: 1, scores: { hook: 50, payoff: 0 } as never }]);
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(resolveMetricValue(lines[1].series[0])).toBe(0);
  });
});

describe("legend / caption / combo copy", () => {
  it("exposes fixed legend strings and non-cumulative hint", () => {
    expect(HOOK_STRENGTH_LABEL).toBe("悬念强度");
    expect(PAYOFF_STRENGTH_LABEL).toBe("本场回应强度");
    expect(PAYOFF_NOT_CUMULATIVE_HINT).toContain("不是累计完成比例");
  });

  it("formats scene caption without 完成XX%", () => {
    const viz = minimalViz([{ scene_ordinal: 1, scores: { hook: 50, payoff: 30 } as never }]);
    const summary = buildHookPayoffSceneSummary(viz, viz.scene_nodes[0]);
    expect(summary).not.toBeNull();
    const caption = formatHookPayoffSceneCaption(summary!);
    expect(caption).toContain("场景 S01");
    expect(caption).toContain("悬念 50");
    expect(caption).toContain("回应 30");
    expect(caption).not.toMatch(/完成\s*30%/);
    expect(payoffPlainLanguage(30)).toContain("核心问题仍未兑现");
  });

  it("builds combination explanations", () => {
    expect(hookPayoffCombinationExplanation(80, 20)).toContain("尚未得到回答");
    expect(hookPayoffCombinationExplanation(20, 80)).toContain("解释、回收或结果兑现");
    expect(hookPayoffCombinationExplanation(null, 50)).toContain("数据不足");
  });
});

describe("question lifecycle + diagnosis filter", () => {
  it("surfaces question_lifecycle for a scene", () => {
    const viz = minimalViz([
      { scene_ordinal: 1 },
      { scene_ordinal: 3 },
      { scene_ordinal: 6 },
    ]);
    viz.question_lifecycle = [
      {
        question_id: "Q1",
        question_text: "石牛角为什么不能倒？",
        setup_scene: 1,
        development_scenes: [3],
        payoff_scene: 6,
        status: "paid_off",
        strength: 0.9,
      },
    ];
    expect(getQuestionLifecycle(viz)).toHaveLength(1);
    expect(questionsForScene(getQuestionLifecycle(viz), 3)[0].question_id).toBe("Q1");
  });

  it("filters plot/tension diagnoses off the hook_payoff primary band", () => {
    expect(
      primaryBandLabelForHookPayoffLens({
        scene_ordinal: 2,
        primary_diagnosis: "plot_stagnation",
        secondary_diagnoses: ["empty_hook"],
      }),
    ).toBe("空悬念");
    expect(
      primaryBandLabelForHookPayoffLens({
        scene_ordinal: 3,
        primary_diagnosis: "plot_stagnation",
      }),
    ).toBe("未发现明显异常");
  });

  it("hook_payoff segment markers exclude 推进停滞 / 张力下降", () => {
    const markers = buildSegmentMarkers(
      [
        {
          scene_ordinal: 1,
          reading_momentum: 80,
          plot_progress: 70,
          reading_tension: 70,
          hook: 80,
          payoff: 20,
        },
        {
          scene_ordinal: 2,
          reading_momentum: 40,
          plot_progress: 30,
          reading_tension: 30,
          hook: 82,
          payoff: 22,
        },
      ],
      { lensId: "hook_payoff" },
    );
    expect(markers.every((m) => !["推进停滞", "张力下降", "冲突升级"].includes(m.label))).toBe(
      true,
    );
  });
});

describe("Beat exclusion and phase averages", () => {
  it("keeps Beat on visual polyline; equal-weight means still skip Beat", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 70, payoff: 20 } as never },
      {
        scene_ordinal: 2,
        role: "beat",
        node_type: "beat",
        include_in_main_curve: false,
        scores: { hook: 99, payoff: 99 } as never,
      },
      { scene_ordinal: 3, scores: { hook: 40, payoff: 60 } as never },
    ]);
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(mainCurveSeries(lines[0].series).map((p) => p.scene_ordinal)).toEqual([1, 2, 3]);
    expect(equalWeightMainCurveSeries(lines[0].series).map((p) => p.scene_ordinal)).toEqual([
      1, 3,
    ]);
  });

  it("phase averages ignore Beat nodes", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 80, payoff: 20 } as never },
      {
        scene_ordinal: 2,
        role: "beat",
        scores: { hook: 0, payoff: 0 } as never,
      },
      { scene_ordinal: 3, scores: { hook: 40, payoff: 60 } as never },
    ]);
    const avg = phaseHookPayoffAverages(viz, {
      start_scene_ordinal: 1,
      end_scene_ordinal: 3,
    });
    expect(avg.avgHook).toBe(60);
    expect(avg.avgPayoff).toBe(40);
  });

  it("builds at most three chapter bullets for hook_payoff", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 90, payoff: 10 } as never },
      { scene_ordinal: 2, scores: { hook: 40, payoff: 80 } as never },
    ]);
    expect(buildHookPayoffChapterBullets(viz)).toHaveLength(3);
  });
});

describe("CSS legend contract", () => {
  it("readerJourney.css defines fixed hook/payoff legend classes", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const css = fs.readFileSync(
      path.join(__dirname, "readerJourney.css"),
      "utf8",
    );
    expect(css).toContain(".journey-hook-payoff-legend");
    expect(css).toContain(".journey-legend-swatch-hook");
    expect(css).toContain(".journey-legend-swatch-payoff");
    expect(css).toContain("border-top-style: dashed");
  });
});
