import { describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  SCENE_CARD_MAX_ROLE_TAGS,
  buildSceneRoleTags,
} from "./sceneCardRoleTags";

function baseViz(overrides: Partial<ReaderJourneyVisualization> = {}): ReaderJourneyVisualization {
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
        scene_count: 3,
        phase_count: 1,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 3,
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
    scene_nodes: [
      { scene_id: 1, scene_ordinal: 1, role: "core", scores: { hook: 80, payoff: 10 } },
      { scene_id: 2, scene_ordinal: 2, role: "core", scores: { hook: 20, payoff: 80 } },
      { scene_id: 3, scene_ordinal: 3, role: "core", scores: { hook: 10, payoff: 10 } },
    ],
    curve_series: {},
    phases: [],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [
      { scene_ordinal: 1 },
      { scene_ordinal: 2 },
      { scene_ordinal: 3 },
    ],
    payoff_markers: [
      { scene_ordinal: 1 },
      { scene_ordinal: 2 },
      { scene_ordinal: 3 },
    ],
    risk_intervals: [{ start_scene_ordinal: 1, end_scene_ordinal: 3, risk_type: "low_engagement" }],
    narrative_loops: [],
    reading_resistance: [],
    ...overrides,
  } as unknown as ReaderJourneyVisualization;
}

describe("buildSceneRoleTags", () => {
  it("does not show tags from markers/scores alone", () => {
    const tags = buildSceneRoleTags(baseViz(), 1);
    expect(tags).toEqual([]);
  });

  it("shows 钩子 only when NarrativeLoop establishes hook at scene", () => {
    const viz = baseViz({
      narrative_loops: [
        {
          loop_id: "L1",
          scope: {},
          question: "他是谁",
          information_gap: "身份",
          hook: [{ scene_ordinal: 1, type: "new", summary: "身份疑问" }],
          developments: [],
          payoffs: [],
          residual_question: "",
          status: "open",
          evidence: [],
          confidence: 0.8,
          consistency_status: "consistent",
          conflicts: [],
          open_from_scene: 1,
        },
      ],
    } as any);
    const tags = buildSceneRoleTags(viz, 1);
    expect(tags.some((t) => t.kind === "hook" && t.label === "钩子")).toBe(true);
    expect(buildSceneRoleTags(viz, 3)).toEqual([]);
  });

  it("shows payoff labels only for legal loop payoff types", () => {
    const viz = baseViz({
      narrative_loops: [
        {
          loop_id: "L1",
          scope: {},
          question: "q",
          information_gap: "g",
          hook: [{ scene_ordinal: 1, type: "new" }],
          developments: [],
          payoffs: [
            { scene_ordinal: 2, type: "partial", summary: "一点线索" },
            { scene_ordinal: 3, type: "score_inferred", source_type: "score_inferred" },
          ],
          residual_question: "",
          status: "partially_resolved",
          evidence: [],
          confidence: 0.7,
          consistency_status: "consistent",
          conflicts: [],
          open_from_scene: 1,
        },
      ],
    } as any);
    expect(buildSceneRoleTags(viz, 2).some((t) => t.label === "部分回报")).toBe(true);
    expect(buildSceneRoleTags(viz, 3).some((t) => t.kind === "payoff")).toBe(false);
  });

  it("shows 明确回报 for full payoff", () => {
    const viz = baseViz({
      narrative_loops: [
        {
          loop_id: "L2",
          scope: {},
          question: "q",
          information_gap: "g",
          hook: [{ scene_ordinal: 1, type: "new" }],
          developments: [],
          payoffs: [{ scene_ordinal: 2, type: "full" }],
          residual_question: "",
          status: "resolved",
          evidence: [],
          confidence: 0.9,
          consistency_status: "consistent",
          conflicts: [],
          open_from_scene: 1,
        },
      ],
    } as any);
    expect(buildSceneRoleTags(viz, 2).map((t) => t.label)).toContain("明确回报");
  });

  it("shows resistance only with real reading_resistance reason", () => {
    const viz = baseViz({
      reading_resistance: [
        {
          start_scene_ordinal: 2,
          end_scene_ordinal: 2,
          reason_codes: ["weak_progress"],
          reasons_zh: ["推进较弱"],
          summary: "推进偏弱",
        },
      ],
    } as any);
    const tags = buildSceneRoleTags(viz, 2);
    expect(tags.some((t) => t.kind === "resistance" && t.label.includes("推进较弱"))).toBe(true);
    expect(buildSceneRoleTags(viz, 1).some((t) => t.kind === "resistance")).toBe(false);
  });

  it("caps ordinary cards at two role tags", () => {
    const viz = baseViz({
      narrative_loops: [
        {
          loop_id: "L1",
          scope: {},
          question: "q",
          information_gap: "g",
          hook: [{ scene_ordinal: 2, type: "new" }],
          developments: [],
          payoffs: [{ scene_ordinal: 2, type: "partial" }],
          residual_question: "",
          status: "partially_resolved",
          evidence: [],
          confidence: 0.8,
          consistency_status: "consistent",
          conflicts: [],
          open_from_scene: 2,
        },
      ],
      reading_resistance: [
        {
          start_scene_ordinal: 2,
          end_scene_ordinal: 2,
          reason_codes: ["long_transition"],
          reasons_zh: ["过渡偏长"],
        },
      ],
    } as any);
    const tags = buildSceneRoleTags(viz, 2);
    expect(tags.length).toBeLessThanOrEqual(SCENE_CARD_MAX_ROLE_TAGS);
    expect(tags.every((t) => t.kind === "hook" || t.kind === "payoff")).toBe(true);
  });
});
