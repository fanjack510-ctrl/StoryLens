/**
 * CHG-20260722-009: continuous reading-momentum polyline regressions.
 * Captures the real chart model (series count / points / path segments).
 */
import { describe, expect, it } from "vitest";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import {
  buildLensChartLines,
  equalWeightMainCurveSeries,
  mainCurveSeries,
} from "./observationLenses";
import { buildLinePathD, resolveMetricValue, xForSceneOrdinal } from "./journeyChartScales";

function node(
  ordinal: number,
  momentum: number,
  role: "core" | "beat",
): JourneySceneNode {
  return {
    scene_id: 100 + ordinal,
    scene_ordinal: ordinal,
    paragraph_range: {
      start_paragraph_id: `P${ordinal}A`,
      end_paragraph_id: `P${ordinal}B`,
    },
    paragraph_count: 4,
    phase_ordinal: ordinal,
    role,
    node_type: role === "beat" ? "beat" : "scene",
    include_in_main_curve: role !== "beat",
    importance_score: role === "core" ? 70 : 20,
    importance_formula_version: "1.1",
    deterministic_reasons: [],
    scene_value_summary: `S${ordinal}`,
    dominant_emotion: "紧张",
    engagement: { engagement_score: Math.round(momentum) },
    scores: { reading_momentum: momentum, curiosity: 50, tension: 50 },
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
  } as unknown as JourneySceneNode;
}

function vizFrom(
  scores: Array<{ momentum: number; role: "core" | "beat" }>,
): ReaderJourneyVisualization {
  const scene_nodes = scores.map((item, index) =>
    node(index + 1, item.momentum, item.role),
  );
  const titles = ["开端", "发展", "收束"];
  return {
    visualization_version: "1.1",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "测试章",
      one_sentence_diagnosis: "测试",
      peak_scene_ordinal: 1,
      valley_scene_ordinal: scores.length,
      average_engagement: 60,
      primary_reader_question: "?",
      emotional_arc_summary: "",
      pacing_summary: "",
      risk_summary: "",
      continuation_motivation: "",
      confidence: 0.8,
    },
    scene_nodes,
    phases: scores.map((_, index) => ({
      ordinal: index + 1,
      title: titles[index] || `阶段${index + 1}`,
      start_scene_ordinal: index + 1,
      end_scene_ordinal: index + 1,
      primary_reader_question: "",
      dominant_emotion: "",
      reading_payoff: "",
      continuation_motivation: "",
      summary: "",
      confidence: 0.8,
      average_engagement: scores[index].momentum,
      core_scene_count: scores[index].role === "core" ? 1 : 0,
      beat_count: scores[index].role === "beat" ? 1 : 0,
      scene_span: 1,
    })),
    curve_series: {
      engagement: scene_nodes.map((n) => ({
        scene_ordinal: n.scene_ordinal,
        value: n.engagement.engagement_score,
        include_in_main_curve: n.include_in_main_curve,
        node_type: n.node_type,
      })),
      valence: [],
      arousal: [],
      curiosity: [],
      tension: [],
      payoff: [],
      hook: [],
      dropoff_risk: [],
    },
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    question_chains: [],
    question_clusters: [],
    suppressed_hooks: [],
    suppressed_question_clusters: [],
  } as unknown as ReaderJourneyVisualization;
}

function chartModel(visualization: ReaderJourneyVisualization) {
  const lines = buildLensChartLines(visualization, "composite");
  const series = lines[0]?.series ?? [];
  const polyline = mainCurveSeries(series);
  const equalWeight = equalWeightMainCurveSeries(series);
  const chartWidth = 640;
  const sceneCount = visualization.scene_nodes.length;
  const path = buildLinePathD(
    polyline,
    (ordinal) => xForSceneOrdinal(ordinal, sceneCount, chartWidth),
    (value) => 200 - value,
  );
  return {
    lineCount: lines.length,
    lineIds: lines.map((line) => line.id),
    seriesPoints: series.map((point) => ({
      scene_ordinal: point.scene_ordinal,
      value: resolveMetricValue(point),
      include_in_main_curve: (point as { include_in_main_curve?: boolean })
        .include_in_main_curve,
      node_type: (point as { node_type?: string }).node_type,
    })),
    polylineOrdinals: polyline.map((point) => point.scene_ordinal),
    equalWeightOrdinals: equalWeight.map((point) => point.scene_ordinal),
    path,
    hasLineTo: /L /.test(path),
    moveCount: path.match(/M /g)?.length ?? 0,
  };
}

describe("reading momentum continuous line (CHG-20260722-009)", () => {
  it("captures chart model for 65/59/54 with one core + two beats", () => {
    const model = chartModel(
      vizFrom([
        { momentum: 65, role: "core" },
        { momentum: 59, role: "beat" },
        { momentum: 54, role: "beat" },
      ]),
    );
    // series[0] = S1 65 core; series[1]=S2 59 beat; series[2]=S3 54 beat
    expect(model.lineCount).toBe(1);
    expect(model.lineIds).toEqual(["reading_momentum"]);
    expect(model.seriesPoints).toEqual([
      {
        scene_ordinal: 1,
        value: 65,
        include_in_main_curve: true,
        node_type: "scene",
      },
      {
        scene_ordinal: 2,
        value: 59,
        include_in_main_curve: false,
        node_type: "beat",
      },
      {
        scene_ordinal: 3,
        value: 54,
        include_in_main_curve: false,
        node_type: "beat",
      },
    ]);
    expect(model.polylineOrdinals).toEqual([1, 2, 3]);
    expect(model.equalWeightOrdinals).toEqual([1]);
    expect(model.hasLineTo).toBe(true);
    expect(model.moveCount).toBe(1);
  });

  it("keeps one continuous series across 开端/发展/收束 phases", () => {
    const model = chartModel(
      vizFrom([
        { momentum: 65, role: "core" },
        { momentum: 59, role: "core" },
        { momentum: 54, role: "core" },
      ]),
    );
    expect(model.lineCount).toBe(1);
    expect(model.polylineOrdinals).toHaveLength(3);
    expect(model.hasLineTo).toBe(true);
  });

  it("single scene only moves, no L segment", () => {
    const model = chartModel(vizFrom([{ momentum: 70, role: "core" }]));
    expect(model.polylineOrdinals).toEqual([1]);
    expect(model.hasLineTo).toBe(false);
    expect(model.moveCount).toBe(1);
  });

  it("two scenes produce one continuous segment", () => {
    const model = chartModel(
      vizFrom([
        { momentum: 70, role: "core" },
        { momentum: 40, role: "beat" },
      ]),
    );
    expect(model.polylineOrdinals).toEqual([1, 2]);
    expect(model.hasLineTo).toBe(true);
  });

  it("missing reading_momentum creates an explicit break (no fabricated bridge)", () => {
    const visualization = vizFrom([
      { momentum: 65, role: "core" },
      { momentum: 59, role: "core" },
      { momentum: 54, role: "core" },
    ]);
    const lines = buildLensChartLines(visualization, "composite");
    lines[0].series[1] = { scene_ordinal: 2, value: undefined };
    const path = buildLinePathD(
      lines[0].series,
      (ordinal) => xForSceneOrdinal(ordinal, 3, 640),
      (value) => 200 - value,
    );
    expect(path.match(/M /g)?.length).toBe(2);
    expect(path.includes("L ")).toBe(false);
  });
});
