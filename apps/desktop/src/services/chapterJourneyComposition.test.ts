import { describe, expect, it } from "vitest";
import {
  isSceneAnalysisComplete,
  mapChapterCompositionState,
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
  it("requires succeeded + scene counts", () => {
    expect(isSceneAnalysisComplete(run({ id: 5 }))).toBe(true);
    expect(
      isSceneAnalysisComplete(
        run({ id: 5, status: "scene_analysis_running", completed_scene_count: 12 }),
      ),
    ).toBe(false);
  });
});
