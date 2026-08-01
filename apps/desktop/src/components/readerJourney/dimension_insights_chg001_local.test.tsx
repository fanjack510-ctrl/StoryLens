/**
 * CHG-20260729-001 — dimension-specific scene insights UI tests.
 */
import { describe, expect, it, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { OBSERVATION_LENSES, compositeRoleFitLabel } from "./observationLenses";
import { formatLensPhaseScoreLabel, resolveLensMetricBinding } from "./lensMetricBinding";
import { getLensExplanation } from "./readerJourneyLensExplanation";
import {
  dimensionInsightTitle,
  resolveDimensionInsightText,
} from "./dimensionInsights";
import { JourneySceneDetailPanel } from "./JourneySceneDetailPanel";
import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { useDeveloperModeStore } from "../../stores/developerModeStore";

const REQUIRED_LABELS = [
  "综合阅读",
  "剧情推进",
  "阅读张力",
  "情绪强度",
  "钩子回收",
  "节奏速度",
];

function buildNode(overrides: Partial<JourneySceneNode> = {}): JourneySceneNode {
  return {
    scene_id: 1,
    scene_ordinal: 1,
    paragraph_range: { start_paragraph_id: "P1", end_paragraph_id: "P2" },
    paragraph_count: 2,
    phase_ordinal: 1,
    role: "core",
    importance_score: 50,
    importance_formula_version: "1.0",
    deterministic_reasons: [],
    scene_value_summary: "测试场景摘要",
    dominant_emotion: "紧张",
    engagement: { engagement_score: 60 },
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
      arousal_end: 50,
      reading_momentum: 62,
      plot_progress: 58,
      reading_tension: 44,
      pacing_speed: 55,
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
    evidence_paragraph_ids: ["P1"],
    evidence_count: 1,
    confidence: 0.8,
    primary_payoff: null,
    primary_hook: null,
    primary_risk: null,
    scene_role: "setup",
    dimension_insights: {
      overall_reading: "综合阅读场景洞察 A。",
      plot_progression: "剧情推进场景洞察 B。",
      reading_tension: "阅读张力场景洞察 C。",
      emotional_intensity: "情绪强度场景洞察 D。",
      hook_payoff: "钩子回收场景洞察 E。",
      pacing_speed: "节奏速度场景洞察 F。",
    },
    insight_source: "generated",
    ...overrides,
  };
}

function minimalViz(node: JourneySceneNode): ReaderJourneyVisualization {
  return {
    scene_nodes: [node],
    phases: [],
    curve_series: { engagement: [{ scene_ordinal: 1, value: 60 }] },
    question_clusters: [],
    question_chains: [],
    risk_intervals: [],
    hook_markers: [],
    payoff_markers: [],
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "测试章",
      diagnosis: "",
      primary_traction: "",
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: 1,
        phase_count: 0,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 1,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 60 },
        engagement_valley: { scene_ordinal: 1, value: 60 },
        engagement_average: 60,
      },
      expanded_diagnosis: {},
    },
    formula_versions: {
      visualization_version: "1.0",
      chain_rank_formula_version: "1.0",
      importance_formula_version: "1.0",
      chain_merge_formula_version: "1.0",
      engagement_formula_version: "1.0",
    },
    calibration_status: {
      scene_contract_version: "2.0",
      source_mode: "local_fixture",
    },
  } as ReaderJourneyVisualization;
}

describe("CHG-20260729-001 dimension insights", () => {
  beforeEach(() => {
    useDeveloperModeStore.setState({ developerMode: false });
  });

  it("keeps six Chinese dimension labels unchanged", () => {
    const labels = OBSERVATION_LENSES.map((item) => item.labelZh);
    expect(labels).toEqual(REQUIRED_LABELS);
  });

  it("uses required composite one-line summary", () => {
    expect(getLensExplanation("composite").one_line_summary).toBe(
      "综合阅读：综合判断每个场景对剧情理解、阅读期待、情绪体验和阅读流畅度的整体贡献。",
    );
  });

  it("uses 综合阅读 for composite phase label", () => {
    const viz = minimalViz(buildNode());
    const label = formatLensPhaseScoreLabel(viz, "composite", 77);
    expect(label).toBe("综合阅读 77");
    const binding = resolveLensMetricBinding(viz, "composite", buildNode());
    expect(binding.labelZh).toBe("综合阅读");
    expect(binding.fieldKey).toBe("reading_momentum");
  });

  it("exposes six insight titles", () => {
    for (const lens of OBSERVATION_LENSES) {
      expect(dimensionInsightTitle(lens.id)).toBe(`${lens.labelZh}洞察`);
    }
  });

  it("switches lens insight text for the same scene", () => {
    const node = buildNode();
    expect(resolveDimensionInsightText(node, "composite")).toContain("综合阅读");
    expect(resolveDimensionInsightText(node, "plot_progress")).toContain("剧情推进");
    expect(resolveDimensionInsightText(node, "reading_tension")).toContain("阅读张力");
  });

  it("shows unavailable copy when insight missing", () => {
    const node = buildNode({ dimension_insights: { overall_reading: null } });
    expect(resolveDimensionInsightText(node, "composite")).toBe("当前维度暂无可靠洞察");
  });

  it("renders simplified scene panel without old tabs", () => {
    const node = buildNode();
    render(
      <JourneySceneDetailPanel
        node={node}
        visualization={minimalViz(node)}
        observationLens="composite"
        onLocateEvidence={() => undefined}
      />,
    );
    expect(screen.queryByTestId("scene-detail-tabs")).toBeNull();
    expect(screen.getByTestId("scene-dimension-insight-text")).toHaveTextContent("综合阅读");
    expect(screen.getByText("综合阅读洞察")).toBeTruthy();
    expect(screen.queryByTestId("scene-detail-score-bars")).toBeNull();
    expect(screen.queryByTestId("scene-detail-tech-details")).toBeNull();
  });

  it("keeps developer details collapsed by default", () => {
    useDeveloperModeStore.setState({ developerMode: true });
    const node = buildNode();
    render(
      <JourneySceneDetailPanel
        node={node}
        visualization={minimalViz(node)}
        observationLens="composite"
        onLocateEvidence={() => undefined}
      />,
    );
    const details = screen.getAllByTestId("scene-detail-tech-details")[0];
    expect(details).toBeTruthy();
    expect((details as HTMLDetailsElement).open).toBe(false);
  });

  it("compositeRoleFitLabel maps null momentum to 无法判断", () => {
    expect(compositeRoleFitLabel(null, "setup")).toBe("无法判断");
    expect(compositeRoleFitLabel(50, "setup")).toBe("合适");
  });
});
