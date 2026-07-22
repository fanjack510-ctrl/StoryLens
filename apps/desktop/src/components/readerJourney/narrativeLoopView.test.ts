import { describe, expect, it } from "vitest";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  HARD_BLOCK_USER_MESSAGE,
  SOFT_CONFLICT_USER_MESSAGE,
  formatHookHandoffFromLoops,
  formatOpenLoopRiskSummary,
  formatPayoffClaimLabel,
  getNarrativeLoopRisks,
  getNarrativeLoops,
  getScenePayoffClaim,
  loopsForScene,
} from "./narrativeLoopView";
import { buildSegmentMarkers } from "./journeySegmentMarkers";

function minimalViz(overrides: Partial<ReaderJourneyVisualization> = {}): ReaderJourneyVisualization {
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
      counts: { scene_count: 2, phase_count: 1, question_chain_count: 0, canonical_chain_count: 0, core: 2, secondary: 0, beat: 0 },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 50 },
        engagement_valley: { scene_ordinal: 2, value: 40 },
        engagement_average: 45,
      },
      expanded_diagnosis: {},
    },
    phases: [],
    curve_series: {
      engagement: [],
      valence: [],
      arousal: [],
      curiosity: [],
      tension: [],
      payoff: [],
      hook: [],
      dropoff_risk: [],
    },
    scene_nodes: [
      {
        scene_id: 1,
        scene_ordinal: 1,
        paragraph_range: { start_paragraph_id: "p1", end_paragraph_id: "p1" },
        paragraph_count: 1,
        phase_ordinal: 1,
        role: "core",
        importance_score: 1,
        importance_formula_version: "1",
        deterministic_reasons: [],
        scene_value_summary: "s1",
        dominant_emotion: "紧张",
        engagement: { engagement_score: 50 },
        scores: {
          curiosity: 40,
          tension: 40,
          payoff: 20,
          hook: 80,
          information_gain: 40,
          emotional_resonance: 40,
          cognitive_load: 40,
          dropoff_risk: 40,
          valence_start: 0,
          valence_end: 0,
          arousal_start: 40,
          arousal_end: 40,
        },
        reader_question_in: [],
        reader_question_created: [{ question: "门外是谁" }],
        reader_question_answered: [],
        reader_question_out: [{ question: "门外是谁" }],
        payoffs: [],
        hooks: [
          {
            type: "danger",
            summary: "门外有人",
            strength: 80,
            gap: "门外是谁",
            evidence_paragraph_ids: ["p1"],
          },
        ],
        techniques: [],
        risk_points: [],
        character_effects: [],
        writing_takeaways: [],
        evidence_paragraph_ids: ["p1"],
        evidence_count: 1,
        confidence: 0.7,
        primary_payoff: null,
        primary_hook: {
          type: "danger",
          summary: "门外有人",
          strength: 80,
          gap: "门外是谁",
          evidence_paragraph_ids: ["p1"],
        },
        primary_risk: null,
      },
      {
        scene_id: 2,
        scene_ordinal: 2,
        paragraph_range: { start_paragraph_id: "p2", end_paragraph_id: "p2" },
        paragraph_count: 1,
        phase_ordinal: 1,
        role: "core",
        importance_score: 1,
        importance_formula_version: "1",
        deterministic_reasons: [],
        scene_value_summary: "s2",
        dominant_emotion: "紧张",
        engagement: { engagement_score: 55 },
        scores: {
          curiosity: 40,
          tension: 40,
          payoff: 85,
          hook: 30,
          information_gain: 40,
          emotional_resonance: 40,
          cognitive_load: 40,
          dropoff_risk: 30,
          valence_start: 0,
          valence_end: 0,
          arousal_start: 40,
          arousal_end: 40,
        },
        reader_question_in: [{ question: "门外是谁" }],
        reader_question_created: [],
        reader_question_answered: [{ question: "门外是谁", answer_summary: "是邻居", answer_degree: "full" }],
        reader_question_out: [],
        payoffs: [
          {
            type: "information",
            summary: "是邻居",
            strength: 85,
            evidence_paragraph_ids: ["p2"],
          },
        ],
        hooks: [],
        techniques: [],
        risk_points: [],
        character_effects: [],
        writing_takeaways: [],
        evidence_paragraph_ids: ["p2"],
        evidence_count: 1,
        confidence: 0.8,
        primary_payoff: {
          type: "information",
          summary: "是邻居",
          strength: 85,
          evidence_paragraph_ids: ["p2"],
        },
        primary_hook: null,
        primary_risk: null,
      },
    ],
    role_counts: { core: 2, secondary: 0, beat: 0 },
    primary_question_chain: {
      canonical_id: "cc-1",
      canonical_question: "门外是谁",
      aliases: [],
      source_chain_ids: [],
      created_scene: 1,
      carried_scene_ordinals: [2],
      transformed_scenes: [],
      answered_scene: 2,
      status: "answered",
      strength: 80,
      open_at_chapter_end: false,
      confidence: 0.8,
      merge_reason: "singleton",
      question_type: "information",
      auto_merged: false,
      lifecycle: [],
    },
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [],
    risk_intervals: [],
    formula_versions: {
      visualization_version: "t",
      chain_rank_formula_version: "t",
      importance_formula_version: "t",
      chain_merge_formula_version: "t",
      engagement_formula_version: "t",
    },
    calibration_status: { source_mode: "legacy_adapter", scene_contract_version: "1.3" },
    ...overrides,
  };
}

describe("narrativeLoopView", () => {
  it("builds loops from question chain + entities for full payoff", () => {
    const viz = minimalViz();
    const loops = getNarrativeLoops(viz);
    expect(loops.length).toBeGreaterThan(0);
    const related = loopsForScene(loops, 2);
    expect(related[0]?.status === "resolved" || related[0]?.payoffs.length).toBeTruthy();
    const claim = getScenePayoffClaim(viz, 2);
    expect(claim?.deterministic).toBe(true);
    expect(claim?.claim).toBe("full");
    expect(formatPayoffClaimLabel(claim, 85)).toContain("较强兑现");
  });

  it("marks score-without-entity as soft conflict and not 有效兑现", () => {
    const viz = minimalViz({
      primary_question_chain: null,
      scene_nodes: [
        {
          ...minimalViz().scene_nodes[0],
          scene_ordinal: 3,
          scores: { ...minimalViz().scene_nodes[0].scores, payoff: 90, hook: 20 },
          hooks: [],
          payoffs: [],
          primary_hook: null,
          primary_payoff: null,
          reader_question_created: [],
          reader_question_out: [],
        },
      ],
      scene_payoff_claims: {
        "3": {
          claim: "score_only",
          label: SOFT_CONFLICT_USER_MESSAGE,
          deterministic: false,
          loops: [],
          payoff_types: [],
          evidence_paragraph_ids: [],
        },
      },
    });
    const claim = getScenePayoffClaim(viz, 3);
    expect(claim?.deterministic).toBe(false);
    expect(claim?.label).toBe(SOFT_CONFLICT_USER_MESSAGE);
    expect(formatPayoffClaimLabel(claim, 90)).toBe(SOFT_CONFLICT_USER_MESSAGE);
  });

  it("derives open-loop risks with locatable question and span", () => {
    const viz = minimalViz({
      primary_question_chain: {
        canonical_id: "cc-open",
        canonical_question: "第二张脸是谁",
        aliases: [],
        source_chain_ids: [],
        created_scene: 1,
        carried_scene_ordinals: [2],
        transformed_scenes: [],
        answered_scene: null,
        status: "carried",
        strength: 70,
        open_at_chapter_end: true,
        confidence: 0.7,
        merge_reason: "singleton",
        question_type: "identity",
        auto_merged: false,
        lifecycle: [],
      },
      scene_nodes: minimalViz().scene_nodes.map((node, idx) =>
        idx === 1
          ? {
              ...node,
              payoffs: [],
              primary_payoff: null,
              scores: { ...node.scores, payoff: 15 },
              reader_question_answered: [],
            }
          : node,
      ),
    });
    const risks = getNarrativeLoopRisks(viz);
    const open = risks.find((r) => r.risk_type === "open_narrative_loop");
    expect(open?.question).toContain("第二张脸是谁");
    expect(formatOpenLoopRiskSummary(open!)).toContain("跨越");
  });

  it("uses development scenes as hook continuation when next_handoff missing", () => {
    const viz = minimalViz({
      question_lifecycle: [
        {
          question_id: "Q1",
          question_text: "门外是谁",
          setup_scene: 1,
          development_scenes: [2],
          payoff_scene: null,
          status: "progressing",
        },
      ],
      primary_question_chain: null,
    });
    const handoff = formatHookHandoffFromLoops(getNarrativeLoops(viz), 1);
    expect(handoff.text).toContain("场景 2");
  });

  it("does not emit 有效兑现 segment marker without verified full claim", () => {
    const samples = [
      { scene_ordinal: 1, hook: 40, payoff: 20, reading_momentum: 40 },
      { scene_ordinal: 2, hook: 30, payoff: 90, reading_momentum: 70 },
    ];
    const unverified = buildSegmentMarkers(samples, {
      lensId: "hook_payoff",
      verifiedFullPayoffScenes: new Set(),
    });
    expect(unverified.every((m) => m.label !== "有效兑现")).toBe(true);

    const verified = buildSegmentMarkers(samples, {
      lensId: "hook_payoff",
      verifiedFullPayoffScenes: new Set([2]),
    });
    expect(verified.some((m) => m.label === "有效兑现")).toBe(true);
  });

  it("keeps different run scopes separated via API claims map", () => {
    const vizA = minimalViz({
      scene_payoff_claims: {
        "2": {
          claim: "full",
          label: "有效兑现",
          deterministic: true,
          loops: ["run-a"],
          payoff_types: ["full"],
          evidence_paragraph_ids: ["p2"],
        },
      },
    });
    const vizB = minimalViz({
      scene_payoff_claims: {
        "2": {
          claim: "none",
          label: "未兑现",
          deterministic: true,
          loops: ["run-b"],
          payoff_types: [],
          evidence_paragraph_ids: [],
        },
      },
    });
    expect(getScenePayoffClaim(vizA, 2)?.loops).toEqual(["run-a"]);
    expect(getScenePayoffClaim(vizB, 2)?.loops).toEqual(["run-b"]);
  });
});
