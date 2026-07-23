/**
 * CHG-20260722-014 — Reader Journey terminology & explanation (presentation only).
 */

import { describe, expect, it } from "vitest";
import {
  ALL_METRICS_LABEL,
  CURRENT_PHASE_LABEL,
  HOOK_PAYOFF_LENS_LEGEND,
  NUMERIC_LENS_LEGEND,
  OVERLAY_COMPARE_TITLE,
  READER_JOURNEY_LENS_EXPLANATIONS,
  getLensExplanation,
} from "./readerJourneyLensExplanation";
import { OBSERVATION_LENSES, pacingFitLabel } from "./observationLenses";
import {
  READING_RESISTANCE_HOVER,
  formatJourneyNodeLabel,
  formatJourneySceneLabel,
  formatReadingResistanceLabel,
  formatJourneyMetricLabel,
  roleLabelZh,
  responseDegreeLabelZh,
} from "./journeyUiLabels";

describe("CHG-014/002 Reader Journey terminology", () => {
  it("exposes exact ordinary lens names", () => {
    const labels = OBSERVATION_LENSES.map((l) => l.labelZh);
    expect(labels).toEqual([
      "综合阅读",
      "剧情推进",
      "阅读张力",
      "情绪强度",
      "钩子回收",
      "节奏速度",
    ]);
    expect(OVERLAY_COMPARE_TITLE).toBe("对比指标");
    expect(ALL_METRICS_LABEL).toBe("全部指标");
    expect(CURRENT_PHASE_LABEL).toBe("当前阶段");
  });

  it("keeps one-liner config and how_to_read at most 3 items", () => {
    for (const lens of Object.values(READER_JOURNEY_LENS_EXPLANATIONS)) {
      expect(lens.title).toBeTruthy();
      expect(lens.one_line_summary.length).toBeGreaterThan(8);
      expect(lens.how_to_read).toHaveLength(3);
      expect(lens.high_meaning).toBeTruthy();
      expect(lens.low_meaning).toBeTruthy();
      expect(lens.caution).toBeTruthy();
      expect(lens.legend_items.length).toBeGreaterThan(0);
      expect(getLensExplanation(lens.lens_id).title).toBe(lens.title);
    }
    expect(getLensExplanation("hook_payoff").title).toBe("钩子回收");
    expect(getLensExplanation("composite").one_line_summary).toContain("不代表一定写得差");
    expect(getLensExplanation("emotion").title).toBe("情绪强度");
    expect(getLensExplanation("pacing").title).toBe("节奏速度");
  });

  it("formats Scene/Beat without English Scene/beat/Phase mix", () => {
    expect(formatJourneySceneLabel(7, "核心场景")).toBe("场景07 · 核心场景");
    expect(formatJourneyNodeLabel(7, { role: "core" })).toBe("场景07 · 核心场景");
    expect(formatJourneyNodeLabel(5, { role: "secondary" })).toBe("场景05 · 过渡场景");
    expect(formatJourneyNodeLabel(7, { role: "beat", sceneRole: "transition" })).toBe(
      "节拍07 · 过渡",
    );
    expect(formatJourneyNodeLabel(4, { role: "beat", sceneRole: "reveal" })).toBe(
      "节拍04 · 信息揭示",
    );
    expect(roleLabelZh("beat")).not.toMatch(/节拍节点|Scene|beat/i);
    expect(formatJourneyNodeLabel(7, { role: "beat" })).not.toMatch(/Scene|beat|Phase/i);
  });

  it("maps ordinary terminology without English tech fields", () => {
    expect(formatJourneyMetricLabel("hook")).toBe("钩子");
    expect(formatJourneyMetricLabel("payoff")).toBe("回报");
    expect(formatJourneyMetricLabel("dropoff_risk")).toBe("阅读阻力");
    expect(responseDegreeLabelZh("partial")).toBe("部分回报");
    expect(responseDegreeLabelZh("full")).toBe("明确回报");
    expect(responseDegreeLabelZh("reversal")).toBe("反转回报");
    expect(responseDegreeLabelZh("transformed_question")).toBe("转化回报");
  });

  it("does not show 流失风险 in ordinary labels", () => {
    const blob = JSON.stringify({
      lenses: OBSERVATION_LENSES,
      explanations: READER_JOURNEY_LENS_EXPLANATIONS,
      resistance: formatReadingResistanceLabel("推进较弱"),
      hover: READING_RESISTANCE_HOVER,
    });
    expect(blob).not.toContain("流失风险");
    expect(formatReadingResistanceLabel("推进较弱")).toBe("阅读阻力｜推进较弱");
    expect(formatReadingResistanceLabel("回应不足")).toBe("阅读阻力｜回应不足");
    expect(formatReadingResistanceLabel("过渡偏长")).toBe("阅读阻力｜过渡偏长");
    expect(READING_RESISTANCE_HOVER).toContain("暂时失去继续阅读的动力");
  });

  it("keeps pacing speed/fit split and 无法判断", () => {
    expect(getLensExplanation("pacing").caution).toContain("不表示与曲线的距离");
    expect(pacingFitLabel(null, "aftermath")).toBe("无法判断");
    expect(pacingFitLabel(50, "aftermath")).toBe("合适");
    expect(["合适", "偏快", "偏慢", "无法判断"]).toContain(pacingFitLabel(90, "aftermath"));
  });

  it("keeps legends to one compact row for numeric and hook/payoff lenses", () => {
    expect(NUMERIC_LENS_LEGEND.map((i) => i.label).join("")).toContain("阅读阻力");
    expect(HOOK_PAYOFF_LENS_LEGEND.map((i) => i.label)).toEqual([
      "━ 已回收",
      "┄ 部分回收",
      "─ 未回收",
      "⚠ 有冲突",
    ]);
    expect(NUMERIC_LENS_LEGEND.length).toBeLessThanOrEqual(5);
    expect(HOOK_PAYOFF_LENS_LEGEND.length).toBeLessThanOrEqual(5);
  });
});
