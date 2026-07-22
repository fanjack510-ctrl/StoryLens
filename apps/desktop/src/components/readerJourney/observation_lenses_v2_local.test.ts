/**
 * Local Vitest suite for Reader Journey v2 observation lenses / chart rules.
 * CHG-20260721-012 frontend.
 */
import { describe, expect, it } from "vitest";
import {
  DEFAULT_OBSERVATION_LENS,
  LEGACY_UNCALIBRATED_BANNER,
  V2_LOCAL_FIXTURE_BANNER,
  V2_NATIVE_REAL_BANNER,
  resolveJourneyTopBanner,
  OBSERVATION_LENSES,
  buildLensChartLines,
  getObservationLens,
  isLegacyUncalibratedVisualization,
  mainCurveSeries,
  equalWeightMainCurveSeries,
  pacingFitLabel,
  pacingSegmentLabel,
  valenceDirection,
} from "./observationLenses";
import {
  formatLensBindingCaption,
  formatLensPhaseScoreLabel,
  phaseAverageForLens,
  readingMomentumLabelZh,
  resolveLensMetricBinding,
  seriesValueAtOrdinal,
} from "./lensMetricBinding";
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
      evidence_paragraph_ids: partial.evidence_paragraph_ids ?? [],
      evidence_count: partial.evidence_count ?? (partial.evidence_paragraph_ids?.length ?? 0),
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
  it("excludes beat from equal-weight means but keeps Beat on the visual polyline", () => {
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
    expect(main.map((p) => p.scene_ordinal)).toEqual([1, 2, 3]);
    expect(equalWeightMainCurveSeries(lines[0].series).map((p) => p.scene_ordinal)).toEqual([
      1, 3,
    ]);
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
    expect(mapDiagnosisCodeToBandLabel("empty_hook")).toBe("空悬念");
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
    ).toEqual(["悬念不足", "节奏偏慢"]);
  });

  it("marks boundary anomalies as 场景可能切得过细", () => {
    expect(
      primaryBandLabelForScene({
        scene_ordinal: 8,
        data_quality_issue: "scene_boundary_anomaly",
      }),
    ).toBe("场景可能切得过细");
  });

  it("does not default missing diagnosis to 正常", () => {
    expect(
      primaryBandLabelForScene({
        scene_ordinal: 1,
        primary_diagnosis: null,
      }),
    ).toBe("未发现明显异常");
    expect(
      primaryBandLabelForScene({
        scene_ordinal: 2,
        primary_diagnosis: null,
        legacyUncalibrated: true,
      }),
    ).toBe("旧版数据");
  });

  it("defaults Beat to 辅助节拍", () => {
    expect(
      primaryBandLabelForScene({
        scene_ordinal: 5,
        role: "beat",
        primary_diagnosis: null,
      }),
    ).toBe("辅助节拍");
  });

  it("maps weak_tension to 张力不足", () => {
    expect(mapDiagnosisCodeToBandLabel("weak_tension")).toBe("张力不足");
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

  it("keeps pacing_speed and pacing_fit as distinct semantics", () => {
    // High speed vs aftermath role → 偏快; high fit score can still report 合适.
    expect(pacingFitLabel(90, "aftermath", 40)).toBe("偏快");
    expect(pacingFitLabel(90, "aftermath", 80)).toBe("合适");
    expect(pacingSegmentLabel(40, 60)).toBe("加速");
    expect(pacingSegmentLabel(70, 50)).toBe("减速");
    expect(pacingSegmentLabel(50, 52)).toBe("变化不明显");
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

describe("CHG-20260721-012 verification matrix", () => {
  it("1) composite defaults to a single reading_momentum line", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }, { scene_ordinal: 2 }]);
    const lines = buildLensChartLines(viz, DEFAULT_OBSERVATION_LENS);
    expect(lines).toHaveLength(1);
    expect(lines[0].id).toBe("reading_momentum");
  });

  it("2) all six lenses switch independently on one chart", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }, { scene_ordinal: 2 }]);
    expect(OBSERVATION_LENSES.map((l) => l.id)).toEqual([
      "composite",
      "plot_progress",
      "reading_tension",
      "emotion",
      "hook_payoff",
      "pacing",
    ]);
    for (const lens of OBSERVATION_LENSES) {
      expect(buildLensChartLines(viz, lens.id).length).toBeLessThanOrEqual(2);
    }
  });

  it("3) overlay adds at most one compare line", () => {
    expect(resolveOverlayLines("reading_tension", true).lineCount).toBe(2);
    const viz = minimalViz([{ scene_ordinal: 1 }]);
    expect(
      buildLensChartLines(viz, "reading_tension", { overlayComposite: true }),
    ).toHaveLength(2);
  });

  it("4) emotion journey keeps negative valence", () => {
    const series = [{ scene_ordinal: 1, start: -90, end: -30 }];
    expect(resolveMetricValue(series[0])).toBe(-60);
    const scale = computeYScale(series, 200, "fixed_0_100", valenceYScaleOptions());
    expect(scale.domainMin).toBe(-100);
    expect(collectDataWarnings(series, { min: -100, max: 100 })).toHaveLength(0);
  });

  it("5) hook/payoff shows two linked lines", () => {
    const viz = minimalViz([{ scene_ordinal: 1, scores: { hook: 80, payoff: 20 } as never }]);
    const lines = buildLensChartLines(viz, "hook_payoff");
    expect(lines.map((l) => l.id)).toEqual(["hook", "payoff"]);
  });

  it("6-7) Beat remains on polyline; equal-weight means still skip Beat", () => {
    const viz = minimalViz([
      { scene_ordinal: 1, role: "core", scores: { reading_momentum: 80 } as never },
      {
        scene_ordinal: 2,
        role: "beat",
        node_type: "beat",
        include_in_main_curve: false,
        scene_value_summary: "客厅陷入死寂。",
        scores: { reading_momentum: 5 } as never,
      },
      { scene_ordinal: 3, role: "core", scores: { reading_momentum: 78 } as never },
    ]);
    const series = buildLensChartLines(viz, "composite")[0].series;
    expect(mainCurveSeries(series).map((p) => p.scene_ordinal)).toEqual([1, 2, 3]);
    expect(equalWeightMainCurveSeries(series).map((p) => p.scene_ordinal)).toEqual([1, 3]);
  });

  it("8-10) diagnosis labels for stagnation / empty spin / empty hook", () => {
    expect(mapDiagnosisCodeToBandLabel("plot_stagnation")).toBe("剧情停滞");
    expect(mapDiagnosisCodeToBandLabel("empty_fast_pacing")).toBe("空转");
    expect(mapDiagnosisCodeToBandLabel("empty_hook")).toBe("空悬念");
    expect(mapDiagnosisCodeToBandLabel("delayed_payoff")).toBe("回应延迟");
  });

  it("11-12) peak narrative explains mechanism and keeps evidence hooks", () => {
    const viz = minimalViz([
      {
        scene_ordinal: 1,
        scores: { reading_momentum: 88, hook: 80, payoff: 70 } as never,
        scene_value_summary: "信息连续升级形成峰值",
        positive_mechanism: "effective_payoff",
        evidence_paragraph_ids: ["P0001", "P0002"],
        techniques: [{ name: "信息递进", code: "info_escalate" } as never],
      },
    ]);
    const bullets = buildChapterSummaryBullets(viz, [
      { scene_ordinal: 1, primary_diagnosis: "effective_payoff" },
    ]);
    expect(bullets[0].text).toMatch(/高点|优势|机制/);
    expect(viz.scene_nodes[0].evidence_paragraph_ids.length).toBeGreaterThan(0);
  });

  it("13) legacy visualization shows uncalibrated banner copy", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }]);
    expect(isLegacyUncalibratedVisualization(viz, { contractVersion: "1.3" })).toBe(true);
    expect(LEGACY_UNCALIBRATED_BANNER).toContain("旧版未校准分析");
    expect(resolveJourneyTopBanner(viz, { contractVersion: "1.3" })).toBe(
      LEGACY_UNCALIBRATED_BANNER,
    );
  });

  it("13b) synthetic fixture banner is preferred over legacy copy", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }]);
    viz.calibration_status = {
      scene_contract_version: "2.0",
      source_mode: "local_fixture",
      display_banner: V2_LOCAL_FIXTURE_BANNER,
    };
    expect(isLegacyUncalibratedVisualization(viz)).toBe(false);
    expect(resolveJourneyTopBanner(viz)).toBe(V2_LOCAL_FIXTURE_BANNER);
    expect(resolveJourneyTopBanner(viz)).toContain("合成测试数据");
    expect(resolveJourneyTopBanner(viz)).not.toContain("旧版未校准分析");
    expect(resolveJourneyTopBanner(viz)).not.toContain("牛角坳");
  });

  it("13c) v2 native real banner distinct from synthetic fixture", () => {
    const viz = minimalViz([{ scene_ordinal: 1 }]);
    viz.calibration_status = {
      scene_contract_version: "2.0",
      source_mode: "v2_native",
      display_banner: V2_NATIVE_REAL_BANNER,
    };
    expect(resolveJourneyTopBanner(viz)).toBe(V2_NATIVE_REAL_BANNER);
    expect(resolveJourneyTopBanner(viz)).toContain("V2真实正文分析");
    expect(resolveJourneyTopBanner(viz)).not.toContain("合成测试数据");
    expect(resolveJourneyTopBanner(viz)).not.toContain("旧版未校准分析");
  });

  it("14) fixed 0-100 domain is absolute (no chapter min-max rescale)", () => {
    const series = [
      { scene_ordinal: 1, value: 10 },
      { scene_ordinal: 2, value: 90 },
    ];
    const scale = computeYScale(series, 240, "fixed_0_100");
    expect(scale.domainMin).toBe(0);
    expect(scale.domainMax).toBe(100);
  });
});

describe("lens card binding + reading_momentum terminology", () => {
  it("binds each lens field consistently across phase / caption / series / detail", () => {
    const viz = minimalViz([
      {
        scene_ordinal: 1,
        scene_role: "setup",
        scores: {
          reading_momentum: 71,
          plot_progress: 55,
          reading_tension: 62,
          hook: 80,
          payoff: 25,
          pacing_speed: 48,
          pacing_fit: 70,
          arousal_start: 40,
          arousal_end: 50,
          valence_start: -10,
          valence_end: 20,
        } as never,
      },
      {
        scene_ordinal: 2,
        scene_role: "escalation",
        scores: {
          reading_momentum: 66,
          plot_progress: 60,
          reading_tension: 70,
          hook: 50,
          payoff: 40,
          pacing_speed: 72,
          pacing_fit: 55,
        } as never,
      },
    ]);
    viz.phases = [
      {
        ordinal: 1,
        title: "起",
        start_scene_ordinal: 1,
        end_scene_ordinal: 2,
        primary_reader_question: "",
        dominant_emotion: "",
        reading_payoff: "",
        continuation_motivation: "",
        summary: "阶段摘要",
        confidence: 0.8,
        average_engagement: 99,
        core_scene_count: 2,
        beat_count: 0,
        scene_span: 2,
      },
    ];
    viz.calibration_status = {
      scene_contract_version: "2.0",
      source_mode: "v2_native",
      display_banner: V2_NATIVE_REAL_BANNER,
    };

    expect(readingMomentumLabelZh(viz)).toBe("阅读动力");
    expect(formatLensPhaseScoreLabel(viz, "composite", 68)).toContain("阅读动力");
    expect(formatLensPhaseScoreLabel(viz, "composite", 68)).not.toContain("综合阅读");
    expect(formatLensPhaseScoreLabel(viz, "plot_progress", 58)).toContain("剧情推进");
    expect(formatLensPhaseScoreLabel(viz, "reading_tension", 66)).toContain("阅读张力");

    const phaseAvg = phaseAverageForLens(viz, "composite", viz.phases[0]);
    expect(phaseAvg).toBeCloseTo((71 + 66) / 2, 5);

    for (const lensId of [
      "composite",
      "plot_progress",
      "reading_tension",
      "hook_payoff",
      "pacing",
    ] as const) {
      const seriesVal = seriesValueAtOrdinal(viz, lensId, 1);
      const binding = resolveLensMetricBinding(viz, lensId, viz.scene_nodes[0]);
      expect(binding.value).toBe(seriesVal);
      expect(formatLensBindingCaption(binding)).not.toMatch(/综合阅读|engagement<40/);
    }

    const pacing = resolveLensMetricBinding(viz, "pacing", viz.scene_nodes[0]);
    expect(pacing.fieldKey).toBe("pacing_speed");
    expect(pacing.secondary?.[0]?.fieldKey).toBe("pacing_fit");
    expect(pacing.value).not.toBe(pacing.secondary?.[0]?.value);
  });
});
