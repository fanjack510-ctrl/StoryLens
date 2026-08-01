import { describe, expect, it } from "vitest";
import {
  STOP_CONFIRM_TITLE,
  canShowStopAnalysis,
  cancellationReasonLabel,
  formatCancelDetailHint,
  isCancelledStatus,
  isStoppingStatus,
  taskCancelStatusLabel,
} from "./taskCancellationUi";

describe("taskCancellationUi", () => {
  it("shows stop for running/queued/paused-like", () => {
    expect(canShowStopAnalysis({ status: "running" })).toBe(true);
    expect(canShowStopAnalysis({ status: "queued" })).toBe(true);
    expect(canShowStopAnalysis({ status: "awaiting_provider_recovery" })).toBe(true);
    expect(canShowStopAnalysis({ status: "scene_analysis_running" })).toBe(true);
  });

  it("hides stop for terminal and stopping", () => {
    expect(canShowStopAnalysis({ status: "succeeded" })).toBe(false);
    expect(canShowStopAnalysis({ status: "failed" })).toBe(false);
    expect(canShowStopAnalysis({ status: "cancelled" })).toBe(false);
    expect(canShowStopAnalysis({ status: "cancellation_requested" })).toBe(false);
    expect(canShowStopAnalysis({ status: "stopping" })).toBe(false);
  });

  it("respects can_cancel flag", () => {
    expect(canShowStopAnalysis({ status: "running", can_cancel: false })).toBe(false);
    expect(canShowStopAnalysis({ status: "weird", can_cancel: true })).toBe(true);
  });

  it("maps stopping and cancelled labels", () => {
    expect(taskCancelStatusLabel("cancellation_requested")).toBe("正在停止");
    expect(taskCancelStatusLabel("stopping")).toBe("正在停止");
    expect(taskCancelStatusLabel("cancelled")).toBe("已停止");
    expect(isStoppingStatus("stopping")).toBe(true);
    expect(isCancelledStatus("cancelled")).toBe(true);
  });

  it("maps user_requested reason", () => {
    expect(cancellationReasonLabel("user_requested")).toBe("用户主动停止");
  });

  it("formats partial progress hint", () => {
    const hint = formatCancelDetailHint({
      status: "cancelled",
      completed_scene_count: 5,
      total_scene_count: 13,
      remaining_scene_count: 8,
    });
    expect(hint).toContain("5 / 13");
    expect(hint).toContain("剩余场景：8");
  });

  it("exposes confirm title", () => {
    expect(STOP_CONFIRM_TITLE).toContain("停止");
  });
});
