import { describe, expect, it } from "vitest";
import {
  buildChapterAnalysisPresentationV1,
  shouldShowJourneyNav,
  type ChapterWorkflowState,
} from "./chapterAnalysisPresentation";
import type { Run } from "../types";

function run(partial: Partial<Run>): Run {
  return {
    id: 1,
    task_type: "chapter_analysis",
    subject_type: "chapter",
    subject_id: "10",
    provider: "fake",
    model: "fake",
    status: "running",
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

describe("CHG-017 journey navigation visibility", () => {
  it("boundary_detecting hides journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "running",
      inFlight: true,
      confirmedRevisionId: null,
      lifecycleRun: run({ status: "running", effective_status: "boundary_detection" }),
    });
    expect(p.workflow_state).toBe("boundary_detecting");
    expect(p.show_journey_nav).toBe(false);
    expect(p.redirect_journey_to_progress).toBe(true);
    expect(p.primary_action).toBe("view_progress");
  });

  it("awaiting_scene_confirmation hides journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "awaiting_scene_boundary_confirmation",
      awaitingConfirmation: true,
    });
    expect(p.workflow_state).toBe("awaiting_scene_confirmation");
    expect(p.show_journey_nav).toBe(false);
    expect(p.redirect_journey_to_confirm).toBe(true);
    expect(p.primary_action).toBe("confirm_scenes");
  });

  it("scene_analysis_running hides journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      confirmedRevisionId: 9,
      completedSceneCount: 1,
      totalSceneCount: 3,
      composition: "running",
      inFlight: true,
      lifecycleRun: run({
        status: "scene_analysis_running",
        effective_status: "scene_analysis",
        completed_scene_count: 1,
        total_scene_count: 3,
      }),
    });
    expect(p.workflow_state).toBe("scene_analysis_running");
    expect(p.show_journey_nav).toBe(false);
    expect(p.redirect_journey_to_progress).toBe(true);
    expect(p.status_title).toBe("正在分析场景");
    expect(p.status_description).toContain("全部场景完成后，将自动生成阅读旅程");
    expect(p.primary_action).toBe("view_progress");
  });

  it("waiting_scene_analysis hides journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      confirmedRevisionId: 9,
      composition: "running",
      inFlight: true,
      lifecycleRun: run({
        status: "succeeded",
        journey_status: "queued",
        journey_error_code: "WAITING_SCENE_ANALYSIS",
        effective_status: "scene_analysis",
        completed_scene_count: 1,
        total_scene_count: 3,
      } as Partial<Run>),
    });
    expect(p.workflow_state).toBe("waiting_scene_analysis");
    expect(p.show_journey_nav).toBe(false);
    expect(p.redirect_journey_to_progress).toBe(true);
  });

  it("journey_starting shows journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      confirmedRevisionId: 9,
      completedSceneCount: 3,
      totalSceneCount: 3,
      composition: "awaiting_reader_journey_start",
    });
    expect(p.workflow_state).toBe("journey_starting");
    expect(p.show_journey_nav).toBe(true);
    expect(p.status_title).toContain("阅读旅程");
  });

  it("journey_running shows journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "reader_journey_processing",
      pageView: "active",
    });
    expect(p.workflow_state).toBe("journey_running");
    expect(p.show_journey_nav).toBe(true);
  });

  it("journey_interrupted shows journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "reader_journey_processing",
      pageView: "interrupted",
      canResumeJourney: true,
    });
    expect(p.workflow_state).toBe("journey_interrupted");
    expect(p.show_journey_nav).toBe(true);
  });

  it("journey_succeeded shows journey nav", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "succeeded",
      pageView: "completed",
      chapterComplete: true,
    });
    expect(p.workflow_state).toBe("journey_succeeded");
    expect(p.show_journey_nav).toBe(true);
    expect(p.show_results_nav).toBe(true);
    expect(p.status_title).toBe("阅读旅程已生成");
    expect(p.show_progress_nav).toBe(true);
  });

  it("historical journey does not force journey nav during scene analysis", () => {
    // Presentation has no hasJourney input — current workflow wins.
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      journeyRunId: 99, // historical id present
      confirmedRevisionId: 12,
      completedSceneCount: 0,
      totalSceneCount: 3,
      composition: "running",
      inFlight: true,
      chapterComplete: false,
      lifecycleRun: run({
        status: "scene_analysis_running",
        effective_status: "scene_analysis",
        completed_scene_count: 0,
        total_scene_count: 3,
      }),
    });
    expect(p.workflow_state).toBe("scene_analysis_running");
    expect(p.show_journey_nav).toBe(false);
    expect(shouldShowJourneyNav(p.workflow_state)).toBe(false);
  });

  it("scene complete to journey_starting flips nav on", () => {
    const duringScenes = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      confirmedRevisionId: 1,
      completedSceneCount: 2,
      totalSceneCount: 3,
      composition: "running",
      inFlight: true,
      lifecycleRun: run({
        status: "scene_analysis_running",
        effective_status: "scene_analysis",
      }),
    });
    const afterScenes = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      confirmedRevisionId: 1,
      completedSceneCount: 3,
      totalSceneCount: 3,
      composition: "awaiting_reader_journey_start",
      lifecycleRun: run({
        status: "succeeded",
        journey_status: "starting",
        completed_scene_count: 3,
        total_scene_count: 3,
      }),
    });
    expect(duringScenes.show_journey_nav).toBe(false);
    expect(afterScenes.show_journey_nav).toBe(true);
    expect(afterScenes.workflow_state).toBe("journey_starting");
  });

  it("only journey_* states advertise journey nav", () => {
    const allowed: ChapterWorkflowState[] = [
      "journey_starting",
      "journey_running",
      "journey_interrupted",
      "journey_failed",
      "journey_cancelled",
      "journey_succeeded",
    ];
    const blocked: ChapterWorkflowState[] = [
      "chapter_ready",
      "boundary_detecting",
      "awaiting_scene_confirmation",
      "scene_analysis_running",
      "waiting_scene_analysis",
      "scene_analysis_failed",
    ];
    for (const s of allowed) expect(shouldShowJourneyNav(s)).toBe(true);
    for (const s of blocked) expect(shouldShowJourneyNav(s)).toBe(false);
  });
});
