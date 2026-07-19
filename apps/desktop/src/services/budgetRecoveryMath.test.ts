import { describe, expect, it } from "vitest";
import {
  computeRequestLimitSuggestion,
  estimateFullPipelineRequests,
  fullPipelineRequestShortfall,
} from "./budgetRecoveryMath";

describe("budgetRecoveryMath", () => {
  it("recommends 80 when used=37 remaining=13 need=26 under limit 50", () => {
    const s = computeRequestLimitSuggestion({
      currentDailyRequestLimit: 50,
      remainingRequests: 13,
      requiredWorstRequests: 26,
      dailyCostLimit: 20,
      estimatedStageCost: 0.3,
    });
    expect(s.usedRequests).toBe(37);
    expect(s.minSuggestedLimit).toBe(63);
    expect(s.recommendedLimit).toBe(80);
    expect(s.dailyCostLimit).toBe(20);
    expect(s.estimatedStageCostCap).toBe(0.3);
  });

  it("estimates full pipeline envelope from paragraph density with retry margins", () => {
    const env = estimateFullPipelineRequests({
      expected_request_count: 10,
      worst_case_request_count: 22,
      paragraph_count: 68,
      transition_count: 67,
    });
    expect(env.boundary.worst).toBe(22);
    expect(env.sceneAnalysis.estimatedScenes).toBe(14);
    expect(env.sceneAnalysis.worst).toBe(28);
    expect(env.retryRepairMargin).toBeGreaterThanOrEqual(2);
    expect(env.recoveryMargin).toBeGreaterThanOrEqual(2);
    expect(env.full.worst).toBe(
      env.boundary.worst +
        env.sceneAnalysis.worst +
        env.readerJourney.worst +
        env.retryRepairMargin +
        env.recoveryMargin,
    );
  });

  it("computes request shortfall for create-time precheck", () => {
    expect(
      fullPipelineRequestShortfall({ remainingRequests: 13, fullWorstRequests: 40 }),
    ).toBe(27);
    expect(
      fullPipelineRequestShortfall({ remainingRequests: 50, fullWorstRequests: 40 }),
    ).toBe(0);
  });
});
