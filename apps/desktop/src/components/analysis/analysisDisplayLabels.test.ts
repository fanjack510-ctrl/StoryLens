import { describe, expect, it } from "vitest";
import {
  formatAnalysisFailureReason,
  formatAnalysisStage,
  formatAnalysisStatus,
  formatBoundaryDecision,
  formatBoundaryReasonCode,
  formatCny,
  formatConfidencePercent,
  formatReviewPriority,
  formatReviewStatus,
  formatTokenCount,
} from "./analysisDisplayLabels";

describe("analysisDisplayLabels", () => {
  it("maps analysis status and stage to Chinese", () => {
    expect(formatAnalysisStatus("queued")).toBe("等待开始");
    expect(formatAnalysisStatus("failed")).toBe("分析未完成");
    expect(formatAnalysisStatus("paused")).toBe("分析已暂停");
    expect(formatAnalysisStatus("unknown_xyz")).toBe("未知状态");
    expect(formatAnalysisStage("scene_analysis")).toBe("分析场景");
    expect(formatAnalysisStage(null)).toBe("—");
  });

  it("maps review enums without leaking raw English in helpers", () => {
    expect(formatReviewStatus("in_review")).toBe("审阅中");
    expect(formatReviewPriority("high")).toBe("高置信度");
    expect(formatBoundaryDecision("pending")).toBe("待处理");
    expect(formatConfidencePercent(0.8)).toBe("80%");
  });

  it("maps boundary reason codes for ordinary UI", () => {
    expect(formatBoundaryReasonCode("location_change")).toBe("位置发生变化");
    expect(formatBoundaryReasonCode("time_change")).toBe("时间发生变化");
    expect(formatBoundaryReasonCode("character_goal_change")).toBe("人物目标发生变化");
    expect(formatBoundaryReasonCode("conflict_change")).toBe("冲突发生变化");
    expect(formatBoundaryReasonCode("topic_change")).toBe("叙事重点发生变化");
    expect(formatBoundaryReasonCode("manual")).toBe("人工新增");
    expect(formatBoundaryReasonCode("model")).toBe("模型建议");
    expect(formatBoundaryReasonCode("weird_unknown")).toBe("其他变化");
    expect(formatBoundaryReasonCode(undefined)).toBe("人工新增");
  });

  it("formats money and tokens without faking unknown as zero", () => {
    expect(formatCny(0.12)).toBe("约 0.12 元");
    expect(formatCny(undefined)).toBe("暂无法估算");
    expect(formatTokenCount(15000)).toMatch(/15/);
    expect(formatTokenCount(null)).toBe("暂无法估算");
    expect(formatAnalysisFailureReason("CLOUD_BUDGET_EXCEEDED")).toBe("预算不足");
  });
});
