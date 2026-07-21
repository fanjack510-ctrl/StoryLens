/**
 * Local Vitest suite for Reader Journey v2 observation lenses / chart rules.
 * CHG-20260721-012 frontend.
 */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_OBSERVATION_LENS,
  LEGACY_UNCALIBRATED_BANNER,
  OBSERVATION_LENSES,
  buildLensChartLines,
  getObservationLens,
  isLegacyUncalibratedVisualization,
  mainCurveSeries,
  pacingFitLabel,
  valenceDirection,
} from "./observationLenses";
import { resolveOverlayLines, maxOverlayLineCount } from "./journeyOverlayRules";
import {
  mapDiagnosisCodeToBandLabel,
  primaryBandLabelForScene,
  secondaryBandLabels,
} from "./diagnosisBandModel";
import { resolveNodeVisualStyle } from "./journeyNodeDiagnosisStyle";
import { buildSegmentMarkers } from "./journeySegmentMarkers";
import { buildChapterSummaryBullets } from "./journeyChapterSummary";
import {
  collectDataWarnings,
  computeYScale,
  resolveMetricValue,
  valenceYScaleOptions,
} from "./journeyChartScales";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";

function minimalViz(nodes: Partial<JourneySceneNode>[]): ReaderJourneyVisualization {
  const scene_nodes = nodes.map((partial, index) => {
    const ordinal = partial.scene_ordinal ?? index + 1;
    return {
      scene_id: ordinal,
      scene_ordinal: ordinal,
      paragraph_range: {
        start_paragraph_id: `P${ordinal}`,
        end_paragraph_id: `P${ordinal}`,
      },
      paragraph_count: partial.paragraph_count ?? 5,
      phase_ordinal: 1,
      role: partial.role ?? "core",
      importance_score: 50,
      importance_formula_version: "1.0",
      deterministic_reasons: [],
      scene_value_summary: partial.scene_value_summary ?? `S${ordinal}`,
      dominant_emotion: "紧张",
      engagement: { engagement_score: partial.engagement?.engagement_score ?? 60 },
      scores: {
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
      confidence: partial.confidence ?? 0.8,
      primary_payoff: null,
      primary_hook: null,
      primary_risk: null,
      node_type: partial.node_type,
      include_in_main_curve: partial.include_in_main_curve,
      primary_diagnosis: partial.primary_diagnosis,
      secondary_diagnoses: partial.secondary_diagnoses,
      positive_mechanism: partial.positive_mechanism,
      data_quality_issue: partial.data_quality_issue,
      scene_role: partial.scene_role,
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
    phases: [],
    curve_series: {
      engagement: emptySeries,
      curiosity: emptySeries,
      tension: emptySeries,
      payoff: emptySeries,
      hook: emptySeries,
      dropoff_risk: emptySeries,
      valence: scene_nodes.map((n) => ({
        scene_ordinal: n.scene_ordinal,
        start: n.scores.valence_start,
        end: n.scores.valence_end,
      })),
      arousal: scene_nodes.map((n) => ({
        scene_ordinal: n.scene_ordinal,
        start: n.scores.arousal_start,
        end: n.scores.arousal_end,
      })),
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
      engagement_formula_version: "1.0",
    },
    calibration_status: {
      scene_contract_version: "1.3",
      semantic_source: "legacy",
    },
  } as ReaderJourneyVisualization;
}

describe("observation lenses", () => {
  it("exposes six lenses and defaults to composite", () => {
    expect(OBSERVATION_LENSES).toHaveLength(6);
    expect(DEFAULT_OBSERVATION_LENS).toBe("composite");
    expect(getObservationLens("composite").labelZh).toBe("综合阅读");
  });

  it("builds a single composite line by default", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { reading_momentum: 70 } as never },
      { scene_ordinal: 2, scores: { reading_momentum: 55 } as never },
    ]);
    const lines = buildLensChartLines(viz, "composite");
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toBe("reading_momentum");
  });

  it("switches lenses without creating six charts", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }, { scene_ordinal: 2 }]);
    for (const lens of OBSERVATION_LENSES) {
      const lines = buildLensChartLines(viz, lens.id);
      expect(lines.length).toBeGreaterThanOrEqual(1);
      expect(lines.length).toBeLessThanOrEqual(2);
    }
  });
});

describe("overlay limits", () => {
  it("defaults off and caps at two lines", () => {
    expect(maxOverlayLineCount()).toBe(2);
    expect(resolveOverlayLines("plot_progress", false).lineCount).toBe(1);
    expect(resolveOverlayLines("plot_progress", true).lineCount).toBe(2);
  });

  it("does not add a third line on hook/payoff paired mode", () => {
    const decision = resolveOverlayLines("hook_payoff", true);
    expect(decision.lineCount).toBe(2);
    expect(decision.reason).toBe("hook_payoff_paired");
    const viz = minimalViz([{ scene_ordinal: 1 }, { scene_ordinal: 2 }]);
    const lines = buildLensChartLines(viz, "hook_payoff", { overlayComposite: true });
    expect(lines).toHaveLength(2);
    expect(lines.map((l) => l.id)).toEqual(["hook", "payoff"]);
    expect(lines[0].style).toBe("solid");
    expect(lines[1].style).toBe("dashed");
  });
});

describe("beat auxiliary nodes", () => {
  it("excludes beat from main curve equal-weight vertices", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, role: "core", scores: { reading_momentum: 80 } as never },
      {
        scene_ordinal: 2,
        role: "beat",
        node_type: "beat",
        include_in_main_curve: false,
        scores: { reading_momentum: 10 } as never,
      },
      { scene_ordinal: 3, role: "core", scores: { reading_momentum: 75 } as never },
    ]);
    const lines = buildLensChartLines(viz, "composite");
    const main = mainCurveSeries(lines[0].series);
    expect(main.map((p) => p.scene_ordinal)).toEqual([1, 3]);
    expect(lines[0].series).toHaveLength(3);
  });
});

describe("valence signed axis", () => {
  it("supports -100..+100 and does not treat negatives as 0-100 anomalies", () => {
    const series = [
      { scene_ordinal: 1, start: -80, end: -20 },
      { scene_ordinal: 2, start: -10, end: 40 },
    ];
    expect(resolveMetricValue(series[0])).toBe(-50);
    const scale = computeYScale(series, 240, "fixed_0_100", valenceYScaleOptions());
    expect(scale.domainMin).toBe(-100);
    expect(scale.domainMax).toBe(100);
    const warnings = collectDataWarnings(series, { min: -100, max: 100 });
    expect(warnings).toHaveLength(0);
    const legacyWarnings = collectDataWarnings(series);
    expect(legacyWarnings.some((w) => w.kind === "below_0")).toBe(true);
  });

  it("reports valence direction without clamping negatives to zero", () => {
    const viz = minimalViz([
      {
        scene_ordinal: 1,
        scores: { valence_start: -60, valence_end: 20 } as never,
      },
    ]);
    expect(valenceDirection(viz.scene_nodes[0])).toBe("up");
  });
});

describe("hook/payoff dual lines", () => {
  it("renders hook solid and payoff dashed", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { hook: 80, payoff: 20 } as never },
      { scene_ordinal: 2, scores: { hook: 40, payoff: 75 } as never },
    ]);
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(lines).toHaveLength(2);
    expect(lines[0].style).toBe("solid");
    expect(lines[1].style).toBe("dashed");
  });
});

describe("diagnosis band", () => {
  it("maps primary codes to Chinese band labels and expands secondary", () => {
    expect(mapDiagnosisCodeToBandLabel("plot_stagnation")).toBe("剧情停滞");
    expect(mapDiagnosisCodeToBandLabel("empty_hook")).toBe("空钩子");
    const primary = primaryBandLabelForScene({
      scene_ordinal: 3,
      primary_diagnosis: "weak_progress",
      secondary_diagnoses: ["weak_hook", "pacing_too_slow"],
    });
    expect(primary).toBe("多项风险");
    expect(
      secondaryBandLabels({
        scene_ordinal: 3,
        secondary_diagnoses: ["weak_hook", "pacing_too_slow"],
      }),
    ).toEqual(["钩子不足", "节奏偏慢"]);
  });

  it("marks boundary anomalies as 切分异常", () => {
    expect(
      primaryBandLabelForScene({
        scene_ordinal: 8,
        data_quality_issue: "scene_boundary_anomaly",
      }),
    ).toBe("切分异常");
  });
});

describe("node visuals + pacing + segments + chapter summary", () => {
  it("uses grey square for beat / data quality", () => {
    const style = resolveNodeVisualStyle({
      isBeat: true,
      primaryDiagnosis: "scene_boundary_anomaly",
    });
    expect(style.shape).toBe("square_dot");
    expect(style.colorZh).toBe("灰色");
  });

  it("does not treat fast pacing as automatically good", () => {
    expect(pacingFitLabel(90, "aftermath")).toBe("偏快");
    expect(pacingFitLabel(50, "aftermath")).toBe("合适");
    expect(pacingFitLabel(20, "climax")).toBe("偏慢");
  });

  it("only marks significant segment deltas", () => {
    const markers = buildSegmentMarkers([
      { scene_ordinal: 1, reading_momentum: 40, hook: 30, payoff: 20 },
      { scene_ordinal: 2, reading_momentum: 42, hook: 32, payoff: 22 },
      { scene_ordinal: 3, reading_momentum: 70, hook: 80, payoff: 25 },
    ]);
    expect(markers.some((m) => m.toOrdinal === 2)).toBe(false);
    expect(markers.some((m) => m.toOrdinal === 3 && m.direction === "up")).toBe(true);
  });

  it("builds at most three chapter summary bullets", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, scores: { reading_momentum: 40, hook: 80 } as never },
      { scene_ordinal: 2, scores: { reading_momentum: 85, payoff: 80 } as never },
      { scene_ordinal: 3, scores: { reading_momentum: 35 } as never },
    ]);
    const bullets = buildChapterSummaryBullets(viz, [
      { scene_ordinal: 2, primary_diagnosis: "effective_payoff" },
      { scene_ordinal: 3, primary_diagnosis: "weak_progress" },
    ]);
    expect(bullets.length).toBeLessThanOrEqual(3);
    expect(bullets[0].kind).toBe("advantage");
  });
});

describe("legacy banner", () => {
  it("flags contract 1.x as legacy_uncalibrated and keeps banner copy", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }]);
    expect(isLegacyUncalibratedVisualization(viz)).toBe(true);
    expect(isLegacyUncalibratedVisualization(viz, { contractVersion: "2.0" })).toBe(false);
    expect(LEGACY_UNCALIBRATED_BANNER).toContain("旧版未校准分析");
  });
});
