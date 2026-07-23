import { describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  isSceneBoundaryAnomalyDiagnosis,
  primaryBandLabelForScene,
} from "./diagnosisBandModel";
import { buildChapterSummaryBullets } from "./journeyChapterSummary";

function vizWithValley(valleyOrdinal: number): ReaderJourneyVisualization {
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
        scene_count: 2,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 2,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 90 },
        engagement_valley: { scene_ordinal: valleyOrdinal, value: 10 },
        curiosity_peak: { scene_ordinal: 1, value: 80 },
        tension_peak: { scene_ordinal: 1, value: 70 },
        emotional_peak: { scene_ordinal: 1, value: 60 },
      },
    },
    scene_nodes: [
      {
        scene_id: 1,
        scene_ordinal: 1,
        role: "core",
        scene_value_summary: "高点",
        scores: { reading_momentum: 90, hook: 40, payoff: 40 },
        engagement: { engagement_score: 90 },
      },
      {
        scene_id: 2,
        scene_ordinal: 2,
        role: "core",
        scene_value_summary: "低点",
        scores: { reading_momentum: 10, hook: 20, payoff: 20 },
        engagement: { engagement_score: 10 },
      },
    ],
    curve_series: {},
    phases: [],
    question_chains: [],
    canonical_chains: [],
  } as unknown as ReaderJourneyVisualization;
}

describe("buildChapterSummaryBullets boundary anomaly", () => {
  it("routes scene_boundary_anomaly via stable code, not Chinese label", () => {
    const bullets = buildChapterSummaryBullets(vizWithValley(2), [
      {
        scene_ordinal: 1,
        primary_diagnosis: "effective_payoff",
        reading_momentum: 90,
        plot_progress: 80,
      },
      {
        scene_ordinal: 2,
        data_quality_issue: "scene_boundary_anomaly",
        reading_momentum: 10,
        plot_progress: 10,
      },
    ]);
    const problem = bullets.find((b) => b.kind === "problem");
    expect(problem?.text).toContain("场景可能切得过细");
    expect(problem?.text).toContain("数据质量");
    expect(problem?.text).not.toContain("切分异常");
    expect(problem?.text).not.toContain("需回看证据");
  });

  it("keeps ordinary valley copy for non-boundary labels", () => {
    const bullets = buildChapterSummaryBullets(vizWithValley(2), [
      {
        scene_ordinal: 1,
        primary_diagnosis: "effective_payoff",
        reading_momentum: 90,
        plot_progress: 80,
      },
      {
        scene_ordinal: 2,
        primary_diagnosis: "weak_progress",
        reading_momentum: 10,
        plot_progress: 10,
      },
    ]);
    const problem = bullets.find((b) => b.kind === "problem");
    expect(problem?.text).toContain("推进偏弱");
    expect(problem?.text).toContain("需回看证据");
    expect(problem?.text).not.toContain("数据质量");
  });

  it("display label can change without breaking code gate", () => {
    const diag = {
      scene_ordinal: 2,
      data_quality_issue: "scene_boundary_anomaly" as const,
    };
    expect(isSceneBoundaryAnomalyDiagnosis(diag)).toBe(true);
    expect(primaryBandLabelForScene(diag)).toBe("场景可能切得过细");
    // Internal gate must not depend on the Chinese string value.
    expect(isSceneBoundaryAnomalyDiagnosis({
      scene_ordinal: 2,
      primary_diagnosis: "weak_progress",
    })).toBe(false);
  });

  it("does not treat other DiagnosisBandLabel as boundary anomaly", () => {
    expect(
      isSceneBoundaryAnomalyDiagnosis({
        scene_ordinal: 1,
        primary_diagnosis: "plot_stagnation",
      }),
    ).toBe(false);
    expect(
      isSceneBoundaryAnomalyDiagnosis({
        scene_ordinal: 1,
        primary_diagnosis: "empty_hook",
      }),
    ).toBe(false);
  });
});
