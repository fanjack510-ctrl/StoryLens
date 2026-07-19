import { describe, expect, it } from "vitest";
import type { Run } from "../../types";
import {
  isTerminalUiState,
  mapRunToUiState,
  progressCounts,
  stageSteps,
  uiStateLabel,
} from "./mapAnalysisUiState";

function run(partial: Partial<Run>): Run {
  return {
    id: 55,
    subject_id: "2",
    provider: "fake",
    model: "fake",
    status: "running",
    progress_current: 0,
    progress_total: 0,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-01-01T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    ...partial,
  };
}

describe("mapAnalysisUiState", () => {
  it("maps backend statuses to UI composition states", () => {
    expect(mapRunToUiState(run({ status: "scene_analysis_running" }))).toBe("running");
    expect(mapRunToUiState(run({ status: "awaiting_boundary_review" }))).toBe(
      "boundary_review_required",
    );
    expect(mapRunToUiState(run({ status: "scene_analysis_partial" }))).toBe("partial");
    expect(mapRunToUiState(run({ status: "awaiting_provider_recovery" }))).toBe(
      "provider_recovery",
    );
    expect(mapRunToUiState(run({ status: "boundary_confirmed_budget_blocked" }))).toBe(
      "awaiting_budget_adjustment",
    );
    expect(
      mapRunToUiState(
        run({
          status: "failed",
          failed_stage: "scene_analysis_budget",
          error_code: "INSUFFICIENT_BUDGET_RESERVATION",
        }),
      ),
    ).toBe("awaiting_budget_adjustment");
    expect(mapRunToUiState(run({ status: "failed_provider" }))).toBe("failed");
    expect(mapRunToUiState(run({ status: "succeeded" }))).toBe("succeeded");
    expect(mapRunToUiState(run({ status: "cancelled" }))).toBe("cancelled");
  });

  it("exposes user-facing labels without internal jargon", () => {
    expect(uiStateLabel("running")).toBe("正在分析本章");
    expect(uiStateLabel("provider_recovery")).toBe("分析已暂停");
    expect(uiStateLabel("aborted_by_limit")).toBe("分析已暂停");
    expect(uiStateLabel("awaiting_budget_adjustment")).toBe("分析已暂停");
    expect(uiStateLabel("succeeded")).toBe("Scene与阅读旅程已完成");
    expect(uiStateLabel("awaiting_reader_journey_start")).toBe("分析已暂停");
    expect(uiStateLabel("reader_journey_processing")).toBe("正在生成阅读旅程");
    expect(uiStateLabel("failed")).toBe("分析已暂停");
    expect(JSON.stringify(uiStateLabel("running"))).not.toMatch(/pipeline|invocation|artifact/i);
    expect(uiStateLabel("awaiting_budget_adjustment")).not.toMatch(
      /provider_disconnected|INSUFFICIENT_BUDGET/i,
    );
  });

  it("stops terminal polling states", () => {
    expect(isTerminalUiState("succeeded")).toBe(true);
    expect(isTerminalUiState("failed")).toBe(true);
    expect(isTerminalUiState("running")).toBe(false);
  });

  it("prefers scene progress counts when available", () => {
    expect(
      progressCounts(
        run({
          completed_scene_count: 3,
          total_scene_count: 14,
          progress_current: 1,
          progress_total: 2,
        }),
      ),
    ).toEqual({ current: 3, total: 14 });
  });

  it("builds stage checklist without inventing backend stages", () => {
    const steps = stageSteps("boundary_review_required");
    expect(steps.map((s) => s.label)).toContain("等待边界审阅");
    expect(steps.find((s) => s.id === "analyze")?.tone).toBe("active");
  });
});
