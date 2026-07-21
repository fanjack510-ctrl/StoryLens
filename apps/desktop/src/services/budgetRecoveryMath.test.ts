import { describe, expect, it } from "vitest";
import {
  classifyCreateBudgetBlockers,
  computeRequestLimitSuggestion,
  estimateFullPipelineRequests,
  estimatedRequestShortfall,
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

  it("hard-gates on estimated shortfall, not worst-case", () => {
    expect(
      estimatedRequestShortfall({ remainingRequests: 7, estimatedRequests: 7 }),
    ).toBe(0);
    expect(
      estimatedRequestShortfall({ remainingRequests: 7, estimatedRequests: 14 }),
    ).toBe(7);
    expect(
      fullPipelineRequestShortfall({ remainingRequests: 7, fullWorstRequests: 14 }),
    ).toBe(7);
  });

  it("screenshot case: stage1 estimated fits → no hard blockers", () => {
    const envelope = estimateFullPipelineRequests({
      expected_request_count: 7,
      worst_case_request_count: 14,
      paragraph_count: 42,
      transition_count: 41,
    });
    const blockers = classifyCreateBudgetBlockers({
      remainingRequests: 7,
      remainingTokens: 74114,
      remainingCost: 4.47905,
      envelope,
      stage1EstimatedRequests: 7,
      stage1EstimatedTokens: 9895,
      stage1EstimatedCost: 0.052046,
      stage1WorstRequests: 14,
      stage1WorstTokens: 22197,
      stage1WorstCost: 0.14385,
      providerConnected: true,
      apiKeyConfigured: true,
    });
    expect(blockers).toEqual([]);
    expect(envelope.full.worst).toBeGreaterThan(7);
  });

  it("blocks when stage1 estimated requests exceed remaining", () => {
    const envelope = estimateFullPipelineRequests({
      expected_request_count: 10,
      worst_case_request_count: 20,
      paragraph_count: 42,
    });
    const blockers = classifyCreateBudgetBlockers({
      remainingRequests: 7,
      remainingTokens: 74114,
      remainingCost: 4.47905,
      envelope,
      stage1EstimatedRequests: 10,
      stage1EstimatedTokens: 9895,
      stage1EstimatedCost: 0.052046,
      providerConnected: true,
      apiKeyConfigured: true,
    });
    expect(blockers.some((b) => b.dimension === "requests")).toBe(true);
    expect(blockers.find((b) => b.dimension === "requests")?.required).toBe(10);
  });
});
