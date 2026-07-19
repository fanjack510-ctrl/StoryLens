import { describe, expect, it } from "vitest";
import type { Run } from "../types";
import {
  chapterProgressHref,
  chapterResultHref,
  discoverActiveChapterRun,
} from "./discoverActiveChapterRun";

function run(partial: Partial<Run>): Run {
  return {
    id: 1,
    subject_id: "2",
    provider: "aliyun_qwen_plus",
    model: "qwen",
    status: "failed",
    progress_current: 0,
    progress_total: 0,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-07-19T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    ...partial,
  };
}

describe("discoverActiveChapterRun", () => {
  it("prefers budget-paused Run #5 over older failed runs for chapter 2", () => {
    const runs = [
      run({ id: 1, status: "failed", created_at: "2026-07-18T01:00:00Z" }),
      run({ id: 2, status: "failed", created_at: "2026-07-18T02:00:00Z" }),
      run({ id: 3, status: "failed", created_at: "2026-07-18T03:00:00Z" }),
      run({ id: 4, status: "failed", created_at: "2026-07-18T04:00:00Z" }),
      run({
        id: 5,
        status: "boundary_confirmed_budget_blocked",
        error_code: "INSUFFICIENT_BUDGET_RESERVATION",
        failed_stage: "scene_analysis_budget",
        created_at: "2026-07-19T01:00:00Z",
        total_scene_count: 13,
        completed_scene_count: 0,
      }),
    ];
    expect(discoverActiveChapterRun(runs, 2)?.id).toBe(5);
  });

  it("does not bind chapter-2 run when querying another chapter", () => {
    const runs = [
      run({
        id: 5,
        subject_id: "2",
        status: "boundary_confirmed_budget_blocked",
        error_code: "INSUFFICIENT_BUDGET_RESERVATION",
      }),
      run({ id: 9, subject_id: "3", status: "scene_analysis_running" }),
    ];
    expect(discoverActiveChapterRun(runs, 3)?.id).toBe(9);
    expect(discoverActiveChapterRun(runs, 2)?.id).toBe(5);
    expect(discoverActiveChapterRun(runs, 1)).toBeNull();
  });

  it("prefers processing over succeeded for same chapter", () => {
    const runs = [
      run({ id: 8, status: "succeeded", created_at: "2026-07-19T03:00:00Z" }),
      run({
        id: 7,
        status: "scene_analysis_running",
        created_at: "2026-07-19T02:00:00Z",
      }),
    ];
    expect(discoverActiveChapterRun(runs, 2)?.id).toBe(7);
  });

  it("falls back to latest succeeded then latest failed", () => {
    expect(
      discoverActiveChapterRun(
        [
          run({ id: 1, status: "failed" }),
          run({ id: 3, status: "succeeded" }),
          run({ id: 2, status: "failed" }),
        ],
        2,
      )?.id,
    ).toBe(3);
    expect(
      discoverActiveChapterRun(
        [run({ id: 1, status: "failed" }), run({ id: 4, status: "failed" })],
        2,
      )?.id,
    ).toBe(4);
  });

  it("builds chapter progress deep link", () => {
    expect(
      chapterProgressHref({ bookId: 1, chapterId: 2, analysisRunId: 5 }),
    ).toBe("/books/1?chapter=2&analysisRun=5&view=progress");
  });

  it("builds chapter result deep link with optional journey tab", () => {
    expect(
      chapterResultHref({ bookId: 1, chapterId: 2, analysisRunId: 5 }),
    ).toBe("/books/1?chapter=2&analysisRun=5&view=result");
    expect(
      chapterResultHref({
        bookId: 1,
        chapterId: 2,
        analysisRunId: 5,
        tab: "reader-journey",
      }),
    ).toBe("/books/1?chapter=2&analysisRun=5&view=result&tab=reader-journey");
  });
});
