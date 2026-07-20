import { describe, expect, it } from "vitest";
import {
  formatJourneyMetricLabel,
  formatJourneyPhaseFallbackSummary,
  formatJourneyPhaseLabel,
  formatJourneySceneLabel,
  formatJourneyScore,
  formatJourneySelectionType,
  formatJourneyStatus,
  isEffectivePhaseSummary,
  PRIMARY_JOURNEY_METRICS,
  resolvePhaseSummaryDisplay,
} from "./journeyUiLabels";

describe("journeyUiLabels display formatters", () => {
  it("maps phase short keys without changing originals", () => {
    expect(formatJourneyPhaseLabel("入")).toBe("入局");
    expect(formatJourneyPhaseLabel("推")).toBe("推进");
    expect(formatJourneyPhaseLabel("转")).toBe("转折");
    expect(formatJourneyPhaseLabel("收")).toBe("收束");
    expect(formatJourneyPhaseLabel("入局")).toBe("入局");
    expect(formatJourneyPhaseLabel(undefined)).toBe("未知阶段");
    expect(formatJourneyPhaseLabel("null")).toBe("未知阶段");
  });

  it("uses fixed fallback phase explanations only", () => {
    expect(formatJourneyPhaseFallbackSummary("入")).toContain("阅读期待");
    expect(formatJourneyPhaseFallbackSummary("推进")).toContain("核心冲突");
    expect(formatJourneyPhaseFallbackSummary("收束")).toContain("后续期待");
  });

  it("rejects punctuation-only phase summaries", () => {
    expect(isEffectivePhaseSummary(".")).toBe(false);
    expect(isEffectivePhaseSummary("。")).toBe(false);
    expect(isEffectivePhaseSummary("   ")).toBe(false);
    expect(isEffectivePhaseSummary(null)).toBe(false);
    expect(isEffectivePhaseSummary(undefined)).toBe(false);
    expect(isEffectivePhaseSummary("建立背景")).toBe(true);
    expect(resolvePhaseSummaryDisplay(".", "入局")).toContain("阅读期待");
    expect(resolvePhaseSummaryDisplay("  ", "推进")).toContain("核心冲突");
    expect(resolvePhaseSummaryDisplay(null, "转折")).toContain("信息变化");
    expect(resolvePhaseSummaryDisplay("真实阶段说明", "推进")).toBe("真实阶段说明");
  });

  it("maps metrics and scores safely", () => {
    expect(formatJourneyMetricLabel("engagement")).toBe("阅读牵引");
    expect(formatJourneyMetricLabel("arousal")).toBe("情绪强度");
    expect(formatJourneyMetricLabel("tension")).toBe("节奏变化");
    expect(formatJourneyMetricLabel("hook")).toBe("钩子强度");
    expect(formatJourneyMetricLabel("nope")).toBe("未知指标");
    expect(formatJourneyScore(76.4)).toBe("76");
    expect(formatJourneyScore(undefined)).toBe("—");
    expect(formatJourneyScore(Number.NaN)).toBe("—");
    expect(PRIMARY_JOURNEY_METRICS).toEqual(["engagement", "arousal", "tension", "hook"]);
  });

  it("formats scene / selection / status without dirty tokens", () => {
    expect(formatJourneySceneLabel(4, "地下仓库")).toBe("场景 04 · 地下仓库");
    expect(formatJourneySceneLabel(undefined)).toBe("场景");
    expect(formatJourneySelectionType("phase")).toBe("阶段");
    expect(formatJourneySelectionType("scene")).toBe("场景");
    expect(formatJourneyStatus("succeeded")).toBe("已完成");
    expect(formatJourneyStatus("running")).toBe("生成中");
    expect(formatJourneyStatus(null)).toBe("—");
  });
});
