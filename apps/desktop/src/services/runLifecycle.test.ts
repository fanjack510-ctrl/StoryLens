import { describe, expect, it } from "vitest";
import {
  existingRunDetailsFromError,
  isNativeOverviewRun,
  normalizeRunLifecycle,
  resolveTaskCenterPrimaryAction,
  selectChapterReentryRun,
  selectNativeOverviewReentryRun,
} from "./runLifecycle";
import type { Run } from "../types";

function run(partial: Partial<Run> & { id: number }): Run {
  return {
    subject_id: "1304",
    subject_type: "chapter",
    task_type: "scene_pipeline",
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
    created_at: "2026-07-26T00:00:00Z",
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
    ...partial,
  } as Run;
}

describe("normalizeRunLifecycle", () => {
  it("maps analyzing → active", () => {
    expect(normalizeRunLifecycle(run({ id: 14, status: "analyzing", subject_type: "book", task_type: "whole_book_overview" }))).toBe(
      "active",
    );
  });

  it("maps scene_analysis_running → active", () => {
    expect(normalizeRunLifecycle(run({ id: 13, status: "scene_analysis_running" }))).toBe("active");
  });

  it("maps completed → completed", () => {
    expect(
      normalizeRunLifecycle(
        run({ id: 12, status: "completed", subject_type: "book", task_type: "whole_book_overview" }),
      ),
    ).toBe("completed");
  });

  it("maps succeeded → completed even without chapter_complete", () => {
    expect(
      normalizeRunLifecycle(run({ id: 1, status: "succeeded", chapter_complete: false })),
    ).toBe("completed");
  });

  it("maps succeeded → completed when treatSucceededAsCompleted (compat)", () => {
    expect(
      normalizeRunLifecycle(run({ id: 1, status: "succeeded", chapter_complete: true }), {
        treatSucceededAsCompleted: true,
      }),
    ).toBe("completed");
  });

  it("keeps confirmed-review + scene_analysis_running as active", () => {
    expect(normalizeRunLifecycle(run({ id: 13, status: "scene_analysis_running" }))).toBe("active");
  });

  it("maps awaiting_boundary_review → awaiting_user", () => {
    expect(normalizeRunLifecycle(run({ id: 2, status: "awaiting_boundary_review" }))).toBe(
      "awaiting_user",
    );
  });

  it("maps failed → failed", () => {
    expect(normalizeRunLifecycle(run({ id: 3, status: "failed" }))).toBe("failed");
  });
});

describe("select reentry runs", () => {
  it("prefers active chapter run over completed", () => {
    const picked = selectChapterReentryRun(
      [
        run({ id: 10, status: "succeeded", chapter_complete: true, created_at: "2026-07-01T00:00:00Z" }),
        run({ id: 13, status: "scene_analysis_running", created_at: "2026-07-26T00:00:00Z" }),
      ],
      1304,
    );
    expect(picked?.id).toBe(13);
  });

  it("prefers native active over completed", () => {
    const picked = selectNativeOverviewReentryRun(
      [
        run({
          id: 12,
          status: "completed",
          subject_type: "book",
          subject_id: "5",
          book_id: 5,
          task_type: "whole_book_overview",
          created_at: "2026-07-26T16:00:00Z",
        }),
        run({
          id: 14,
          status: "analyzing",
          subject_type: "book",
          subject_id: "5",
          book_id: 5,
          task_type: "whole_book_overview",
          created_at: "2026-07-26T17:00:00Z",
        }),
      ],
      5,
    );
    expect(picked?.id).toBe(14);
    expect(isNativeOverviewRun(picked!)).toBe(true);
  });

  it("selects completed native when no active", () => {
    const picked = selectNativeOverviewReentryRun(
      [
        run({
          id: 12,
          status: "completed",
          subject_type: "book",
          subject_id: "5",
          book_id: 5,
          task_type: "whole_book_overview",
        }),
      ],
      5,
    );
    expect(picked?.id).toBe(12);
  });
});

describe("task center primary action", () => {
  it("native completed → 查看结果", () => {
    const a = resolveTaskCenterPrimaryAction(
      run({
        id: 12,
        status: "completed",
        subject_type: "book",
        task_type: "whole_book_overview",
      }),
    );
    expect(a.label).toBe("查看结果");
  });

  it("native analyzing → 查看进度", () => {
    const a = resolveTaskCenterPrimaryAction(
      run({
        id: 14,
        status: "analyzing",
        subject_type: "book",
        task_type: "whole_book_overview",
      }),
    );
    expect(a.label).toBe("查看进度");
  });

  it("chapter succeeded without journey → 查看结果", () => {
    const a = resolveTaskCenterPrimaryAction(
      run({ id: 55, status: "succeeded", chapter_complete: false }),
    );
    expect(a.testId).toBe("view-results-55");
    expect(a.label).toBe("查看结果");
  });

  it("scene_analysis_partial → 查看详情", () => {
    const a = resolveTaskCenterPrimaryAction(run({ id: 55, status: "scene_analysis_partial" }));
    expect(a.testId).toBe("view-detail-55");
    expect(a.label).toBe("查看详情");
  });

  it("scene active → 查看进度", () => {
    const a = resolveTaskCenterPrimaryAction(run({ id: 13, status: "scene_analysis_running" }));
    expect(a.label).toBe("查看进度");
  });

  it("awaiting review → 继续确认", () => {
    const a = resolveTaskCenterPrimaryAction(run({ id: 2, status: "awaiting_boundary_review" }));
    expect(a.label).toBe("继续确认");
  });
});

describe("existingRunDetailsFromError", () => {
  it("reads details from ApiError detail bag", () => {
    const got = existingRunDetailsFromError({
      code: "ANALYSIS_RUN_EXISTS",
      detail: {
        existing_run_id: 13,
        existing_run_status: "scene_analysis_running",
        existing_run_type: "scene_pipeline",
        book_id: 5,
        chapter_id: 1304,
      },
    });
    expect(got?.existing_run_id).toBe(13);
    expect(got?.chapter_id).toBe(1304);
  });

  it("returns null without existing_run_id", () => {
    expect(
      existingRunDetailsFromError({ code: "ANALYSIS_RUN_EXISTS", detail: {} }),
    ).toBeNull();
  });
});
