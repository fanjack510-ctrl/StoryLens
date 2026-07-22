import { describe, expect, it } from "vitest";
import {
  isChapterAnalysisComplete,
  isChapterAnalysisInFlight,
  isSceneAnalysisComplete,
  mapChapterCompositionState,
  resolveChapterWorkspaceView,
} from "./chapterJourneyComposition";
import type { Run } from "../types";

function run(partial: Partial<Run> & { id: number }): Run {
  return {
    subject_id: "2",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status: "succeeded",
    progress_current: 13,
    progress_total: 13,
    execution_mode: "cloud",
    cloud_consent: true,
    sends_content_to_cloud: true,
    retryable: false,
    created_at: "2026-01-01T00:00:00Z",
    reusable_checkpoint_count: 0,
    conflicted_checkpoint_count: 0,
    checkpoint_total_count: 0,
    checkpoint_available: false,
    completed_scene_count: 13,
    total_scene_count: 13,
    ...partial,
  } as Run;
}

describe("mapChapterCompositionState", () => {
  it("marks scene-succeeded without journey as awaiting_reader_journey_start", () => {
    expect(mapChapterCompositionState(run({ id: 5 }), null)).toBe(
      "awaiting_reader_journey_start",
    );
    expect(mapChapterCompositionState(run({ id: 5 }), undefined)).toBe(
      "awaiting_reader_journey_start",
    );
  });

  it("does not claim full chapter success without journey visualization", () => {
    expect(
      mapChapterCompositionState(run({ id: 5 }), {
        status: "succeeded",
        journey_run_id: 9,
        visualization: null,
      }),
    ).toBe("awaiting_reader_journey_start");
  });

  it("maps active journey statuses to reader_journey_processing", () => {
    expect(
      mapChapterCompositionState(run({ id: 5 }), {
        status: "scene_profiles_running",
        journey_run_id: 9,
      }),
    ).toBe("reader_journey_processing");
  });

  it("requires succeeded journey + visualization for full success", () => {
    expect(
      mapChapterCompositionState(run({ id: 5 }), {
        status: "succeeded",
        journey_run_id: 9,
        visualization: { scene_nodes: [] },
      }),
    ).toBe("succeeded");
  });

  it("keeps failed journey recoverable as awaiting start", () => {
    expect(
      mapChapterCompositionState(run({ id: 5 }), {
        status: "failed",
        journey_run_id: 9,
      }),
    ).toBe("awaiting_reader_journey_start");
  });
});

describe("isSceneAnalysisComplete", () => {
  it("requires scene counts when status succeeded", () => {
    expect(
      isSceneAnalysisComplete(
        run({ id: 1, completed_scene_count: 13, total_scene_count: 13 }),
      ),
    ).toBe(true);
  });
});

describe("chapter completeness helpers", () => {
  it("treats scene artifact alone as incomplete chapter", () => {
    const r = run({ id: 1, chapter_complete: false, status: "succeeded" });
    expect(isChapterAnalysisComplete(r)).toBe(false);
    expect(isChapterAnalysisInFlight(r, "awaiting_reader_journey_start")).toBe(true);
    expect(isChapterAnalysisInFlight(r, "reader_journey_processing")).toBe(true);
  });

  it("completes only when chapter_complete is true", () => {
    const r = run({ id: 1, chapter_complete: true, status: "succeeded" });
    expect(isChapterAnalysisComplete(r)).toBe(true);
    expect(isChapterAnalysisInFlight(r, "succeeded")).toBe(false);
  });
});

describe("resolveChapterWorkspaceView", () => {
  it("does not auto-open result while in flight even if Scene exists", () => {
    expect(
      resolveChapterWorkspaceView({
        requestedView: null,
        userPinnedView: null,
        chapterComplete: false,
        inFlight: true,
        composition: "awaiting_reader_journey_start",
      }),
    ).toBe("progress");
  });

  it("rewrites stale view=result to progress unless user pinned result", () => {
    expect(
      resolveChapterWorkspaceView({
        requestedView: "result",
        userPinnedView: null,
        chapterComplete: false,
        inFlight: true,
        composition: "reader_journey_processing",
      }),
    ).toBe("progress");
    expect(
      resolveChapterWorkspaceView({
        requestedView: "result",
        userPinnedView: "result",
        chapterComplete: false,
        inFlight: true,
        composition: "reader_journey_processing",
      }),
    ).toBe("result");
  });

  it("allows complete chapter result view", () => {
    expect(
      resolveChapterWorkspaceView({
        requestedView: "result",
        userPinnedView: null,
        chapterComplete: true,
        inFlight: false,
        composition: "succeeded",
      }),
    ).toBe("result");
  });

  it("honors user reading pin over system complete default", () => {
    expect(
      resolveChapterWorkspaceView({
        requestedView: null,
        userPinnedView: "reading",
        chapterComplete: true,
        inFlight: false,
        composition: "succeeded",
      }),
    ).toBe("reading");
  });

  it("does not auto-open result for historical chapter_complete", () => {
    expect(
      resolveChapterWorkspaceView({
        requestedView: null,
        userPinnedView: null,
        chapterComplete: true,
        inFlight: false,
        composition: "succeeded",
      }),
    ).toBe("reading");
  });
});
