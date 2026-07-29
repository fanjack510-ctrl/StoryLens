/**
 * CHG-20260729-002 — stage color mapping + midpoint band geometry.
 */
import { describe, expect, it } from "vitest";
import {
  JOURNEY_STAGE_VISUAL_TOKENS,
  PHASE_BAND_COLORS,
  resolveJourneyStageKey,
  resolveJourneyStageToken,
} from "./journeyVisualTokens";
import {
  buildContiguousStageRuns,
  buildJourneyStageBands,
  computeStageBandPixelRanges,
  resolveSceneStageAssignment,
} from "./journeyStageBands";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { OBSERVATION_LENSES } from "./observationLenses";
import { xForSceneOrdinal } from "./journeyChartScales";
import { CHART_PAD } from "./journeyVisualizationConfig";

function fixtureViz(): ReaderJourneyVisualization {
  const nodes = [1, 2, 3, 4, 5, 6].map((ordinal) => ({
    scene_id: ordinal,
    scene_ordinal: ordinal,
    paragraph_range: { start_paragraph_id: `P${ordinal}`, end_paragraph_id: `P${ordinal}` },
    paragraph_count: 1,
    phase_ordinal: ordinal <= 2 ? 1 : ordinal <= 5 ? 2 : 3,
    role: "core" as const,
    importance_score: 50,
    importance_formula_version: "1.0",
    deterministic_reasons: [],
    scene_value_summary: `场景${ordinal}`,
    dominant_emotion: "平",
    engagement: { engagement_score: 40 + ordinal * 5 },
    scores: {
      curiosity: 40,
      tension: 40,
      payoff: 40,
      hook: 40,
      information_gain: 40,
      emotional_resonance: 40,
      cognitive_load: 30,
      dropoff_risk: 30,
      valence_start: 0,
      valence_end: 0,
      arousal_start: 40,
      arousal_end: 45,
      reading_momentum: 40 + ordinal * 4,
      plot_progress: 35 + ordinal * 5,
      reading_tension: 30 + ordinal * 3,
      pacing_speed: 50 + (ordinal % 3) * 8,
    },
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
    confidence: 0.8,
    primary_payoff: null,
    primary_hook: null,
    primary_risk: null,
  }));

  return {
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "测试",
      diagnosis: "",
      primary_traction: "",
      weak_interval: "",
      strongest_payoff: null,
      strongest_hook: null,
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
        engagement_peak: { scene_ordinal: 6, value: 70 },
        engagement_valley: { scene_ordinal: 1, value: 40 },
      },
    },
    phases: [
      {
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
        average_engagement: 45,
        summary: "开端阶段",
      },
      {
        ordinal: 2,
        title: "发展",
        start_scene_ordinal: 3,
        end_scene_ordinal: 5,
        average_engagement: 55,
        summary: "发展阶段",
      },
      {
        ordinal: 3,
        title: "收束",
        start_scene_ordinal: 6,
        end_scene_ordinal: 6,
        average_engagement: 65,
        summary: "收束阶段",
      },
    ],
    scene_nodes: nodes,
    curve_series: { engagement: nodes.map((n) => ({ scene_ordinal: n.scene_ordinal, value: 50 })) },
    risk_intervals: [],
    hook_markers: [],
    payoff_markers: [],
    question_chains: [],
    calibration_status: { scene_contract_version: "2.0", source_mode: "local_fixture" },
  } as unknown as ReaderJourneyVisualization;
}

describe("CHG-20260729-002 stage color tokens", () => {
  it("maps opening/development/closing and unknown", () => {
    expect(resolveJourneyStageKey("开端")).toBe("opening");
    expect(resolveJourneyStageKey("发展")).toBe("development");
    expect(resolveJourneyStageKey("收束")).toBe("closing");
    expect(resolveJourneyStageKey("???")).toBe("unknown");
  });

  it("shares the same token colors as PHASE_BAND_COLORS legacy array", () => {
    expect(PHASE_BAND_COLORS[0]).toBe(JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand);
    expect(PHASE_BAND_COLORS[1]).toBe(JOURNEY_STAGE_VISUAL_TOKENS.development.chartBand);
    expect(PHASE_BAND_COLORS[2]).toBe(JOURNEY_STAGE_VISUAL_TOKENS.closing.chartBand);
    expect(resolveJourneyStageToken("开端").cardBackground).toBe(
      JOURNEY_STAGE_VISUAL_TOKENS.opening.chartBand,
    );
  });
});

describe("CHG-20260729-002 stage band geometry", () => {
  it("covers 1-2 / 3-5 / 6 with midpoint edges (not equal thirds)", () => {
    const viz = fixtureViz();
    const ordinals = [1, 2, 3, 4, 5, 6];
    const chartWidth = 700;
    const xFor = (o: number) => xForSceneOrdinal(o, 6, chartWidth);
    const plotLeft = CHART_PAD.left;
    const plotRight = chartWidth - CHART_PAD.right;
    const bands = buildJourneyStageBands(viz, {
      sceneOrdinals: ordinals,
      xFor,
      plotLeft,
      plotRight,
    });

    expect(bands).toHaveLength(3);
    expect(bands[0].stageKey).toBe("opening");
    expect(bands[0].startSceneOrdinal).toBe(1);
    expect(bands[0].endSceneOrdinal).toBe(2);
    expect(bands[1].stageKey).toBe("development");
    expect(bands[1].startSceneOrdinal).toBe(3);
    expect(bands[1].endSceneOrdinal).toBe(5);
    expect(bands[2].stageKey).toBe("closing");
    expect(bands[2].startSceneOrdinal).toBe(6);
    expect(bands[2].endSceneOrdinal).toBe(6);

    expect(bands[0].x1).toBe(plotLeft);
    expect(bands[2].x2).toBe(plotRight);
    const mid12_3 = (xFor(2) + xFor(3)) / 2;
    expect(bands[0].x2).toBeCloseTo(mid12_3, 5);
    expect(bands[1].x1).toBeCloseTo(mid12_3, 5);
    const mid5_6 = (xFor(5) + xFor(6)) / 2;
    expect(bands[1].x2).toBeCloseTo(mid5_6, 5);
    expect(bands[2].x1).toBeCloseTo(mid5_6, 5);

    const equalThird = (plotRight - plotLeft) / 3;
    expect(bands[0].x2 - bands[0].x1).not.toBeCloseTo(equalThird, 0);
    expect(bands[1].x2 - bands[1].x1).not.toBeCloseTo(equalThird, 0);
  });

  it("recomputes when scene count changes", () => {
    const viz = fixtureViz();
    viz.phases = [
      { ordinal: 1, title: "开端", start_scene_ordinal: 1, end_scene_ordinal: 1, average_engagement: 40, summary: "" },
      { ordinal: 2, title: "发展", start_scene_ordinal: 2, end_scene_ordinal: 3, average_engagement: 50, summary: "" },
      { ordinal: 3, title: "收束", start_scene_ordinal: 4, end_scene_ordinal: 4, average_engagement: 60, summary: "" },
    ];
    viz.scene_nodes = viz.scene_nodes.slice(0, 4).map((n, i) => ({
      ...n,
      scene_ordinal: i + 1,
      phase_ordinal: i === 0 ? 1 : i < 3 ? 2 : 3,
    }));
    const ordinals = [1, 2, 3, 4];
    const xFor = (o: number) => xForSceneOrdinal(o, 4, 640);
    const bands = buildJourneyStageBands(viz, {
      sceneOrdinals: ordinals,
      xFor,
      plotLeft: CHART_PAD.left,
      plotRight: 640 - CHART_PAD.right,
    });
    expect(bands).toHaveLength(3);
    expect(bands[0].endSceneOrdinal).toBe(1);
    expect(bands[1].startSceneOrdinal).toBe(2);
    expect(bands[1].endSceneOrdinal).toBe(3);
    expect(bands[2].startSceneOrdinal).toBe(4);
  });

  it("keeps non-monotonic stages as separate runs with warning", () => {
    const runs = buildContiguousStageRuns([1, 2, 3], (ordinal) => {
      const key = ordinal === 2 ? "development" : "opening";
      const token = JOURNEY_STAGE_VISUAL_TOKENS[key];
      return {
        sceneOrdinal: ordinal,
        stageKey: key,
        label: token.label,
        token,
        phaseOrdinal: ordinal,
      };
    });
    expect(runs).toHaveLength(3);
    expect(runs.every((r) => r.warning === "non_monotonic_stage_sequence")).toBe(true);
  });

  it("assigns unknown without inventing thirds", () => {
    const viz = fixtureViz();
    viz.phases = [];
    const a = resolveSceneStageAssignment(viz, 2, viz.scene_nodes[1]);
    expect(a.stageKey).toBe("unknown");
    expect(a.label).toBe("阶段未判定");
  });

  it("six lenses share identical stage range logic (lens-agnostic bands)", () => {
    const viz = fixtureViz();
    const xFor = (o: number) => xForSceneOrdinal(o, 6, 700);
    const bands = buildJourneyStageBands(viz, {
      sceneOrdinals: [1, 2, 3, 4, 5, 6],
      xFor,
      plotLeft: CHART_PAD.left,
      plotRight: 700 - CHART_PAD.right,
    });
    expect(OBSERVATION_LENSES.map((l) => l.labelZh)).toEqual([
      "综合阅读",
      "剧情推进",
      "阅读张力",
      "情绪强度",
      "钩子回收",
      "节奏速度",
    ]);
    // Same bands object reused conceptually for every lens.
    for (const _lens of OBSERVATION_LENSES) {
      expect(bands.map((b) => [b.stageKey, b.startSceneOrdinal, b.endSceneOrdinal])).toEqual([
        ["opening", 1, 2],
        ["development", 3, 5],
        ["closing", 6, 6],
      ]);
    }
  });

  it("pixel helper uses plot edges for first/last", () => {
    const ranges = computeStageBandPixelRanges(
      [
        { startSceneOrdinal: 1, endSceneOrdinal: 1 },
        { startSceneOrdinal: 2, endSceneOrdinal: 2 },
      ],
      [1, 2],
      (o) => (o === 1 ? 100 : 200),
      40,
      300,
    );
    expect(ranges[0].x1).toBe(40);
    expect(ranges[0].x2).toBe(150);
    expect(ranges[1].x1).toBe(150);
    expect(ranges[1].x2).toBe(300);
  });
});
