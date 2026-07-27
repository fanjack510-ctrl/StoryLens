import { describe, expect, it } from "vitest";
import {
  hasChartSafeJourneyNodes,
  hasUsableJourneyVisualization,
  isChartEligibleNode,
} from "./hasUsableJourneyVisualization";
import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";

function viz(
  overrides: Partial<ReaderJourneyVisualization> = {},
): ReaderJourneyVisualization {
  return {
    visualization_version: "4.2",
    chapter_summary: {} as ReaderJourneyVisualization["chapter_summary"],
    phases: [{ ordinal: 1 } as ReaderJourneyVisualization["phases"][number]],
    curve_series: {
      engagement: [{ scene_ordinal: 1, value: 50 }],
    } as ReaderJourneyVisualization["curve_series"],
    scene_nodes: [
      {
        scene_ordinal: 1,
        scores: { reading_momentum: 1, plot_progress: 1 },
        engagement: { engagement_score: 1 },
      } as ReaderJourneyVisualization["scene_nodes"][number],
    ],
    role_counts: { core: 0, secondary: 0, beat: 0 },
    primary_question_chain: null,
    phase_question_chains: [],
    secondary_question_chains: [],
    payoff_markers: [],
    hook_markers: [],
    risk_intervals: [],
    formula_versions: {
      engagement_formula_version: "1.0",
      importance_formula_version: "1.0",
    },
    calibration_status: {},
    ...overrides,
  } as ReaderJourneyVisualization;
}

describe("hasUsableJourneyVisualization", () => {
  it("returns false when status is not succeeded", () => {
    expect(
      hasUsableJourneyVisualization({ status: "failed", visualization: viz() }),
    ).toBe(false);
  });

  it("returns false when scene_nodes / phases / series are empty", () => {
    expect(
      hasUsableJourneyVisualization({
        status: "succeeded",
        visualization: viz({ scene_nodes: [] }),
      }),
    ).toBe(false);
    expect(
      hasUsableJourneyVisualization({
        status: "succeeded",
        visualization: viz({ phases: [] }),
      }),
    ).toBe(false);
    expect(
      hasUsableJourneyVisualization({
        status: "succeeded",
        visualization: viz({
          curve_series: {
            engagement: [],
          } as unknown as ReaderJourneyVisualization["curve_series"],
        }),
      }),
    ).toBe(false);
  });

  it("returns true for succeeded visualization with usable data", () => {
    expect(
      hasUsableJourneyVisualization({ status: "succeeded", visualization: viz() }),
    ).toBe(true);
  });
});

describe("isChartEligibleNode / hasChartSafeJourneyNodes", () => {
  it("treats phase_summary without scores as non-chart, not pollution", () => {
    expect(
      isChartEligibleNode({
        scene_ordinal: 1,
        node_type: "phase_summary",
      }),
    ).toBe(false);
    expect(
      hasChartSafeJourneyNodes({
        status: "succeeded",
        visualization: viz({
          scene_nodes: [
            {
              scene_ordinal: 1,
              node_type: "phase_summary",
            } as unknown as ReaderJourneyVisualization["scene_nodes"][number],
            {
              scene_ordinal: 2,
              scores: { reading_momentum: 2 },
              engagement: { engagement_score: 2 },
            } as unknown as ReaderJourneyVisualization["scene_nodes"][number],
          ],
        }),
      }),
    ).toBe(true);
  });

  it("rejects integrity-blocked chart nodes as ineligible", () => {
    expect(
      isChartEligibleNode({
        scene_ordinal: 1,
        integrity_blocked: true,
        scores: { reading_momentum: 1 },
      }),
    ).toBe(false);
  });

  it("accepts scene nodes with scores", () => {
    expect(hasChartSafeJourneyNodes({ status: "succeeded", visualization: viz() })).toBe(
      true,
    );
  });
});
