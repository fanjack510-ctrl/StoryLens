import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

/** Fixture A — transition / atmosphere chapter with no reliable hooks. */
export function chg005FixtureANoReliableHooks(): ReaderJourneyVisualization {
  return {
    visualization_version: "test",
    chapter_summary: {
      chapter_id: 1,
      chapter_title: "过渡",
      diagnosis: "d",
      primary_traction: "p",
      strongest_payoff: null,
      strongest_hook: null,
      weak_interval: "",
      counts: {
        scene_count: 6,
        phase_count: 2,
        question_chain_count: 0,
        canonical_chain_count: 0,
        core: 6,
        secondary: 0,
        beat: 0,
      },
      peaks: {
        engagement_peak: { scene_ordinal: 1, value: 40 },
        engagement_valley: { scene_ordinal: 3, value: 20 },
        curiosity_peak: { scene_ordinal: 1, value: 30 },
        tension_peak: { scene_ordinal: 1, value: 25 },
        emotional_peak: { scene_ordinal: 1, value: 35 },
      },
    },
    scene_nodes: Array.from({ length: 6 }, (_, i) => ({
      scene_id: i + 1,
      scene_ordinal: i + 1,
      role: "core",
      scene_role: i < 3 ? "setup" : "aftermath",
      scores: {
        hook: i === 4 ? 80 : 20,
        payoff: i === 4 ? 80 : 15,
        reading_momentum: 40,
      },
      engagement: { engagement_score: 40 },
      techniques: [],
      positive_mechanism: i === 4 ? "effective_payoff" : undefined,
      primary_diagnosis: i === 4 ? "effective_payoff" : undefined,
      hooks: [],
      payoffs: [],
      dimension_insights: { hook_payoff: null },
    })),
    curve_series: {},
    phases: [
      {
        ordinal: 1,
        title: "开端",
        start_scene_ordinal: 1,
        end_scene_ordinal: 3,
        average_engagement: 35,
        summary: "",
      },
      {
        ordinal: 2,
        title: "收束",
        start_scene_ordinal: 4,
        end_scene_ordinal: 6,
        average_engagement: 40,
        summary: "",
      },
    ],
    question_chains: [],
    canonical_chains: [],
    hook_markers: [],
    payoff_markers: [],
    risk_intervals: [],
    // Weak / noise loops only — or empty. Include score-ish noise to mirror Fake.
    narrative_loops: [
      {
        loop_id: "noise-1",
        question: "smoke-fake hook for scene 5???",
        open_from_scene: 5,
        hook: [{ scene_ordinal: 5, type: "new", summary: "smoke-fake", strength: 80 }],
        developments: [],
        payoffs: [],
        status: "open",
        display_status: "open",
        consistency_status: "consistent",
        conflicts: [],
        primary_relation: {
          grade: "unsupported",
          payoff_ref: {
            scene_ordinal: 5,
            type: "score_inferred",
            source_type: "score_inferred",
          },
        },
      },
    ],
    reading_resistance: [],
  } as unknown as ReaderJourneyVisualization;
}

/** Fixture A variant with zero loops. */
export function chg005FixtureAEmptyLoops(): ReaderJourneyVisualization {
  const viz = chg005FixtureANoReliableHooks();
  (viz as { narrative_loops: unknown[] }).narrative_loops = [];
  return viz;
}

export { chg005CompleteFixtureViz as chg005FixtureBReliableHooks } from "./chg005CompleteFixture";
