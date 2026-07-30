import { describe, expect, it } from "vitest";
import { buildChapterAnalysisPresentationV1 } from "./chapterAnalysisPresentation";
import type { Run } from "../types";

function run(partial: Partial<Run>): Run {
  return {
    id: 1,
    task_type: "chapter_analysis",
    subject_type: "chapter",
    subject_id: "10",
    provider: "aliyun_qwen_plus",
    model: "qwen3.7-plus",
    status: "succeeded",
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

describe("buildChapterAnalysisPresentationV1", () => {
  it("interrupted excludes running", () => {
    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 1301,
      composition: "reader_journey_processing",
      pageView: "interrupted",
      lifecycleRun: run({
        status: "succeeded",
        journey_status: "interrupted",
        effective_status: "journey_interrupted",
      }),
      inFlight: true,
    });
    expect(presentation.workflow_state).toBe("journey_interrupted");
    expect(presentation.primary_action).toBe("continue_analysis");
  });

  it("interrupted pageView wins over sibling chapterComplete", () => {
    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 3,
      analysisRunId: 3,
      journeyRunId: 2,
      composition: "awaiting_reader_journey_start",
      pageView: "interrupted",
      chapterComplete: true,
      canResumeJourney: true,
      lifecycleRun: run({
        id: 3,
        status: "succeeded",
        journey_status: "succeeded",
        journey_run_id: 5,
        chapter_complete: true,
        effective_status: "completed",
      }),
    });
    expect(presentation.workflow_state).toBe("journey_interrupted");
    expect(presentation.status_title).toBe("阅读旅程已中断");
    expect(presentation.primary_action).toBe("continue_analysis");
    expect(presentation.can_resume).toBe(true);
    expect(presentation.status_title).not.toBe("阅读旅程已完成");
  });

  it("succeeded journey does not expose continue", () => {
    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 3,
      composition: "succeeded",
      pageView: "completed",
      chapterComplete: true,
      canResumeJourney: true,
    });
    expect(presentation.workflow_state).toBe("journey_succeeded");
    expect(presentation.primary_action).toBe("view_results");
    expect(presentation.can_resume).toBe(false);
    expect(presentation.status_title).toBe("阅读旅程已完成");
  });

  it("awaiting hides journey nav", () => {
    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 1301,
      composition: "awaiting_scene_boundary_confirmation",
      awaitingConfirmation: true,
    });
    expect(presentation.workflow_state).toBe("awaiting_scene_confirmation");
    expect(presentation.show_journey_nav).toBe(false);
    expect(presentation.show_confirm_nav).toBe(true);
  });

  it("succeeded primary view_results", () => {
    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 1301,
      composition: "succeeded",
      pageView: "completed",
      chapterComplete: true,
    });
    expect(presentation.workflow_state).toBe("journey_succeeded");
    expect(presentation.primary_action).toBe("view_results");
    expect(presentation.show_results_nav).toBe(true);
  });

  it("show_analysis_nav always false", () => {
    const states = [
      buildChapterAnalysisPresentationV1({
        chapterId: 1,
        composition: "idle",
      }),
      buildChapterAnalysisPresentationV1({
        chapterId: 1,
        composition: "running",
        inFlight: true,
      }),
      buildChapterAnalysisPresentationV1({
        chapterId: 1,
        composition: "awaiting_scene_boundary_confirmation",
        awaitingConfirmation: true,
      }),
      buildChapterAnalysisPresentationV1({
        chapterId: 1,
        composition: "reader_journey_processing",
        pageView: "active",
      }),
      buildChapterAnalysisPresentationV1({
        chapterId: 1,
        composition: "succeeded",
        chapterComplete: true,
      }),
    ];
    for (const presentation of states) {
      expect(presentation.show_analysis_nav).toBe(false);
    }
  });
});
