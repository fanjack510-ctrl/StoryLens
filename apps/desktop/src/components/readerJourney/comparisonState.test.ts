import { describe, expect, it } from "vitest";
import {
  buildComparisonState,
  resolveCompareAfterLensChange,
  sanitizeCompareMetric,
} from "./comparisonState";

describe("comparisonState", () => {
  it("is inactive without compare metric", () => {
    const state = buildComparisonState("emotion", null);
    expect(state.mode).toBe("inactive");
    expect(state.compareMetric).toBeNull();
    expect(state.primaryLabel).toMatch(/情绪/);
  });

  it("is active with valid distinct compare metric", () => {
    const state = buildComparisonState("emotion", "reading_momentum");
    expect(state.mode).toBe("active");
    expect(state.compareMetric).toBe("reading_momentum");
    expect(state.compareLabel).toMatch(/综合阅读/);
  });

  it("clears same-as-primary and illegal compare", () => {
    expect(sanitizeCompareMetric("arousal", "arousal")).toBeNull();
    expect(sanitizeCompareMetric("bogus", "arousal")).toBeNull();
    expect(buildComparisonState("emotion", "arousal").mode).toBe("inactive");
  });

  it("keeps compare when switching to a different lens", () => {
    const next = resolveCompareAfterLensChange("plot_progress", "reading_momentum");
    expect(next.compare).toBe("reading_momentum");
    expect(next.exitedSameMetric).toBe(false);
  });

  it("exits compare when new primary matches compare", () => {
    const next = resolveCompareAfterLensChange("composite", "reading_momentum");
    expect(next.compare).toBeNull();
    expect(next.exitedSameMetric).toBe(true);
  });

  it("clears compare on hook_payoff", () => {
    const next = resolveCompareAfterLensChange("hook_payoff", "arousal");
    expect(next.compare).toBeNull();
    expect(buildComparisonState("hook_payoff", "arousal").mode).toBe("inactive");
  });
});
