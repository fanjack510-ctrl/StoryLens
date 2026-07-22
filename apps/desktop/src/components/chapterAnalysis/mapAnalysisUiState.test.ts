import { describe, expect, it } from "vitest";
import type { Run } from "../../types";
import {
  budgetSummary,
  currentWorkLabel,
  elapsedLabel,
  isTerminalUiState,
  mapRunToUiState,
  progressCounts,
  stageLabelForRun,
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
    expect(uiStateLabel("succeeded")).toBe("分析完成");
    expect(uiStateLabel("awaiting_reader_journey_start")).toBe("场景分析已完成");
    expect(uiStateLabel("reader_journey_processing")).toBe("正在生成阅读旅程");
    expect(uiStateLabel("failed")).toBe("分析未完成");
    expect(JSON.stringify(uiStateLabel("running"))).not.toMatch(/pipeline|invocation|artifact/i);
    expect(uiStateLabel("awaiting_budget_adjustment")).not.toMatch(
      /provider_disconnected|INSUFFICIENT_BUDGET/i,
    );
  });

  it("uses Chinese-only stage labels", () => {
    expect(stageLabelForRun(run({ current_stage: "scene_analysis" }))).toBe("正在分析场景");
    expect(stageLabelForRun(run({ current_stage: "reader_journey" }))).toBe("正在生成阅读旅程");
    expect(stageLabelForRun(run({ current_stage: "scene_analysis" }))).not.toMatch(
      /Scene Analysis|Reader Journey/i,
    );
  });

  it("derives current work labels from ui state and run", () => {
    expect(currentWorkLabel("running", run({ current_stage: "scene_analysis" }))).toBe(
      "正在分析场景",
    );
    expect(currentWorkLabel("failed", run({}))).toBe("分析未完成");
    expect(currentWorkLabel("succeeded", run({}))).toBe("分析完成");
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

  it("builds six-step checklist with boundary review active before analyze", () => {
    const steps = stageSteps("boundary_review_required");
    expect(steps.map((s) => s.label)).toEqual([
      "准备章节",
      "识别场景边界",
      "确认场景划分",
      "分析场景",
      "生成阅读旅程",
      "完成",
    ]);
    expect(steps.find((s) => s.id === "boundary_review")?.tone).toBe("active");
    expect(steps.find((s) => s.id === "analyze")?.tone).toBe("pending");
    expect(steps.find((s) => s.id === "analyze")?.tone).not.toBe("done");
  });

  it("formats budget summary in yuan", () => {
    expect(
      budgetSummary(
        run({
          budget_required: { estimated_cost: 1.2 },
          budget_remaining: { estimated_cost: 0.8 },
        }),
      ),
    ).toBe("约 1.2 元 · 剩余约 0.8 元");
    expect(budgetSummary(run({ budget_required: { estimated_cost: 2 } }))).toBe("约 2 元");
  });

  it("guards elapsed label against invalid or absurd durations", () => {
    expect(elapsedLabel(run({ created_at: "not-a-date" }))).toBeNull();
    expect(
      elapsedLabel(
        run({
          created_at: "2026-01-02T00:00:00Z",
          started_at: "2026-01-02T00:00:00Z",
        }),
      ),
    ).toBe("暂无准确记录");
    expect(
      elapsedLabel(
        run({
          created_at: "2020-01-01T00:00:00Z",
          started_at: "2020-01-01T00:00:00Z",
        }),
      ),
    ).toBe("暂无准确记录");
    expect(
      elapsedLabel(
        run({
          created_at: "2026-01-01T00:00:00Z",
          started_at: "2026-01-01T00:00:00Z",
          completed_at: "2026-01-01T00:05:30Z",
        }),
      ),
    ).toBe("5 分 30 秒");
    // Naive UTC timestamps must not be treated as local (+8h skew).
    expect(
      elapsedLabel(
        run({
          created_at: "2026-07-22 04:31:06.346675",
          started_at: "2026-07-22 04:31:06.346675",
          completed_at: "2026-07-22 04:31:43.710676",
        }),
      ),
    ).toBe("37 秒");
  });
});
