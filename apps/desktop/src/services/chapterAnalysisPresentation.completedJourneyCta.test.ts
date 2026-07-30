import { describe, expect, it } from "vitest";
import {
  buildChapterAnalysisPresentationV1,
  resolveCompletedJourneyNavPrimary,
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

describe("CHG-017 completed journey CTA / nav primary", () => {
  it("1. scene_analysis_running: progress primary, journey hidden", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      analysisRunId: 11,
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
    expect(p.primary_action).toBe("view_progress");
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: p.workflow_state,
        currentView: "progress",
      }),
    ).toBe("view_progress");
  });

  it("2. journey_starting: progress primary, journey secondary visible", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      analysisRunId: 11,
      journeyRunId: 21,
      confirmedRevisionId: 9,
      composition: "awaiting_reader_journey_start",
      lifecycleRun: run({
        status: "succeeded",
        journey_status: "starting",
        completed_scene_count: 3,
        total_scene_count: 3,
      }),
    });
    expect(p.workflow_state).toBe("journey_starting");
    expect(p.show_journey_nav).toBe(true);
    expect(p.primary_action).toBe("view_progress");
    expect(p.status_title).toMatch(/阅读旅程/);
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: p.workflow_state,
        currentView: "progress",
      }),
    ).toBe("view_progress");
  });

  it("3. journey_running: progress primary, journey secondary visible", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      analysisRunId: 11,
      journeyRunId: 21,
      composition: "reader_journey_processing",
      pageView: "active",
      journeyStatus: "running",
    });
    expect(p.workflow_state).toBe("journey_running");
    expect(p.show_journey_nav).toBe(true);
    expect(p.primary_action).toBe("view_progress");
    expect(p.status_title).toBe("正在生成阅读旅程");
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: p.workflow_state,
        currentView: "progress",
      }),
    ).toBe("view_progress");
  });

  it("4. journey_succeeded + progress: reading-journey primary CTA, progress secondary", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      analysisRunId: 11,
      journeyRunId: 21,
      composition: "succeeded",
      pageView: "completed",
      chapterComplete: true,
      journeyStatus: "succeeded",
    });
    expect(p.workflow_state).toBe("journey_succeeded");
    expect(p.status_title).toBe("阅读旅程已生成");
    expect(p.show_journey_nav).toBe(true);
    expect(p.show_progress_nav).toBe(true);
    expect(p.primary_action).toBe("view_results");
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: p.workflow_state,
        currentView: "progress",
      }),
    ).toBe("view_reading_journey");
  });

  it("5. journey_succeeded + reading journey: journey selected, progress not primary", () => {
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: "journey_succeeded",
        currentView: "result",
        resultTab: "journey",
      }),
    ).toBe("none");
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: "journey_succeeded",
        currentView: "result",
        resultTab: "reader-journey",
      }),
    ).toBe("none");
  });

  it("6. journey_succeeded never keeps view_progress as completed nav primary", () => {
    const views = ["progress", "result", "reading"] as const;
    for (const currentView of views) {
      const nav = resolveCompletedJourneyNavPrimary({
        workflowState: "journey_succeeded",
        currentView,
        resultTab: currentView === "result" ? "journey" : null,
      });
      expect(nav).not.toBe("view_progress");
    }
  });

  it("7. running → succeeded auto-recomputes primary without sticky progress", () => {
    const running = resolveCompletedJourneyNavPrimary({
      workflowState: "journey_running",
      currentView: "progress",
    });
    const succeeded = resolveCompletedJourneyNavPrimary({
      workflowState: "journey_succeeded",
      currentView: "progress",
    });
    expect(running).toBe("view_progress");
    expect(succeeded).toBe("view_reading_journey");
  });

  it("8. Ctrl+F5 / cold presentation still prefers journey after succeeded", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 4,
      analysisRunId: 40,
      journeyRunId: 41,
      composition: "succeeded",
      pageView: "completed",
      chapterComplete: true,
      journeyStatus: "succeeded",
      lifecycleRun: run({
        id: 40,
        status: "succeeded",
        journey_status: "succeeded",
        completed_scene_count: 3,
        total_scene_count: 3,
      }),
    });
    expect(p.workflow_state).toBe("journey_succeeded");
    expect(shouldShowJourneyNav(p.workflow_state)).toBe(true);
    expect(
      resolveCompletedJourneyNavPrimary({
        workflowState: p.workflow_state,
        currentView: "progress",
      }),
    ).toBe("view_reading_journey");
  });

  it("does not promote journey primary while still running", () => {
    const states: ChapterWorkflowState[] = [
      "journey_starting",
      "journey_running",
      "scene_analysis_running",
      "waiting_scene_analysis",
    ];
    for (const workflowState of states) {
      expect(
        resolveCompletedJourneyNavPrimary({
          workflowState,
          currentView: "progress",
        }),
      ).toBe("view_progress");
    }
  });
});
