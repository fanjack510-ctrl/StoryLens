import { describe, expect, it } from "vitest";
import { resolveCompositeRunLifecycle } from "./compositeRunLifecycle";
import { formatRunProgress } from "./runProgressDisplay";
import { normalizeRunLifecycle, resolveTaskCenterPrimaryAction } from "./runLifecycle";
import type { Run } from "../types";

function run(partial: Partial<Run> & { id: number }): Run {
  return {
    subject_id: "3",
    subject_type: "chapter",
    task_type: "scene_pipeline",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status: "succeeded",
    progress_current: 1,
    progress_total: 1,
    error_code: null,
    error_message: null,
    root_error_code: null,
    root_error_message: null,
    failed_stage: null,
    failed_invocation_id: null,
    provider_health_at_failure: null,
    retryable: true,
    user_action_hint: null,
    retry_of_run_id: null,
    created_at: "2026-07-27T00:00:00Z",
    queued_at: "",
    started_at: null,
    completed_at: null,
    execution_mode: "cloud",
    analysis_mode: "assisted_boundary_review",
    cloud_consent: true,
    cloud_consent_at: null,
    sends_content_to_cloud: true,
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    total_scene_count: 7,
    completed_scene_count: 7,
    ...partial,
  } as Run;
}

describe("CHG-019 composite lifecycle / progress / CTA", () => {
  it("Parent succeeded + Journey running → active / 阅读旅程 0/7 / 查看进度", () => {
    const r = run({
      id: 2,
      journey_status: "scene_profiles_running",
      journey_completed_scene_count: 0,
      journey_total_scene_count: 7,
      journey_result_available: false,
      effective_status: "journey_running",
    });
    expect(resolveCompositeRunLifecycle({
      parentStatus: r.status,
      journeyStatus: r.journey_status,
      journeyResultAvailable: r.journey_result_available,
      effectiveStatus: r.effective_status,
    })).toBe("active");
    expect(normalizeRunLifecycle(r)).toBe("active");
    expect(formatRunProgress(r)).toBe("阅读旅程：0 / 7");
    expect(resolveTaskCenterPrimaryAction(r).label).toBe("查看进度");
  });

  it("Parent succeeded + Journey interrupted → 阅读旅程已中断 / 查看详情", () => {
    const r = run({
      id: 2,
      journey_status: "failed",
      journey_retryable: true,
      journey_error_code: "JOURNEY_INTERRUPTED",
      journey_result_available: false,
      effective_status: "journey_failed",
    });
    expect(normalizeRunLifecycle(r)).toBe("interrupted");
    expect(formatRunProgress(r)).toBe("阅读旅程已中断");
    expect(resolveTaskCenterPrimaryAction(r).label).toBe("查看详情");
  });

  it("Parent succeeded + Journey completed + artifact → 已完成 / 查看分析结果", () => {
    const r = run({
      id: 2,
      journey_status: "succeeded",
      journey_completed_scene_count: 7,
      journey_total_scene_count: 7,
      journey_result_available: true,
      chapter_complete: true,
      effective_status: "completed",
    });
    expect(normalizeRunLifecycle(r)).toBe("completed");
    expect(formatRunProgress(r)).toBe("阅读旅程：7 / 7");
    expect(resolveTaskCenterPrimaryAction(r).label).toBe("查看分析结果");
  });

  it("Journey succeeded without artifact → must not 查看结果", () => {
    const r = run({
      id: 2,
      journey_status: "succeeded",
      journey_result_available: false,
      chapter_complete: false,
    });
    expect(normalizeRunLifecycle(r)).toBe("interrupted");
    expect(resolveTaskCenterPrimaryAction(r).label).toBe("查看详情");
  });

  it("no Journey + Parent succeeded → scene-only 查看结果", () => {
    const r = run({ id: 55, status: "succeeded", chapter_complete: false });
    expect(normalizeRunLifecycle(r)).toBe("completed");
    expect(formatRunProgress(r)).toBe("场景分析：7 / 7");
    expect(resolveTaskCenterPrimaryAction(r).label).toBe("查看结果");
  });

  it("regressions: scene_analysis_partial / active scene / native hidden by filter elsewhere", () => {
    expect(
      resolveTaskCenterPrimaryAction(run({ id: 55, status: "scene_analysis_partial" })).label,
    ).toBe("查看详情");
    expect(
      resolveTaskCenterPrimaryAction(run({ id: 13, status: "scene_analysis_running" })).label,
    ).toBe("查看进度");
  });
});
