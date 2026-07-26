import { describe, expect, it } from "vitest";
import { resolveChapterPrimaryAction } from "./chapterPrimaryAction";
import type { Run } from "../types";

function run(partial: Partial<Run>): Run {
  return {
    id: 1,
    task_type: "chapter_analysis",
    subject_type: "chapter",
    subject_id: "10",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status: "queued",
    progress_current: 0,
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
    created_at: "",
    queued_at: "",
    started_at: null,
    completed_at: null,
    execution_mode: "cloud",
    analysis_mode: "BALANCED",
    cloud_consent: true,
    cloud_consent_at: null,
    sends_content_to_cloud: true,
    ...partial,
  } as Run;
}

describe("resolveChapterPrimaryAction", () => {
  it("shows 开始分析 when idle", () => {
    const a = resolveChapterPrimaryAction({
      hasChapter: true,
      run: null,
      composition: "idle",
      chapterComplete: false,
      inFlight: false,
    });
    expect(a.kind).toBe("start");
    expect(a.label).toBe("开始分析");
  });

  it("shows 查看分析进度 when running", () => {
    const a = resolveChapterPrimaryAction({
      hasChapter: true,
      run: run({ status: "scene_analysis_running" }),
      composition: "running",
      chapterComplete: false,
      inFlight: true,
    });
    expect(a.kind).toBe("progress");
    expect(a.label).toBe("查看分析进度");
  });

  it("shows 查看分析结果 when chapter complete", () => {
    const a = resolveChapterPrimaryAction({
      hasChapter: true,
      run: run({ status: "succeeded", chapter_complete: true }),
      composition: "succeeded",
      chapterComplete: true,
      inFlight: false,
    });
    expect(a.kind).toBe("result");
    expect(a.label).toBe("查看分析结果");
  });

  it("shows 重新分析 when failed", () => {
    const a = resolveChapterPrimaryAction({
      hasChapter: true,
      run: run({ status: "failed" }),
      composition: "failed",
      chapterComplete: false,
      inFlight: false,
    });
    expect(a.kind).toBe("reanalyze");
    expect(a.label).toBe("重新分析");
  });

  it("does not invent a second journey start action", () => {
    const a = resolveChapterPrimaryAction({
      hasChapter: true,
      run: run({ status: "succeeded", chapter_complete: false }),
      composition: "awaiting_reader_journey_start",
      chapterComplete: false,
      inFlight: true,
    });
    expect(a.kind).toBe("progress");
    expect(a.label).not.toMatch(/读者旅程/);
  });
});
