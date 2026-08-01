import { describe, expect, it } from "vitest";
import {
  mergeBoundJourneyStatus,
  resolveCurrentJourneyExecutionState,
} from "./currentJourneyExecutionState";

describe("mergeBoundJourneyStatus", () => {
  it("terminal detail beats active progress", () => {
    expect(mergeBoundJourneyStatus("failed", "scene_profiles_running")).toBe("failed");
    expect(mergeBoundJourneyStatus("succeeded", "scene_profiles_running")).toBe("succeeded");
    expect(mergeBoundJourneyStatus("cancelled", "running")).toBe("cancelled");
  });

  it("terminal progress beats non-terminal detail", () => {
    expect(mergeBoundJourneyStatus("scene_profiles_partial", "failed")).toBe("failed");
    expect(mergeBoundJourneyStatus("running", "succeeded")).toBe("succeeded");
  });

  it("active progress beats interrupted detail when neither terminal", () => {
    expect(mergeBoundJourneyStatus("scene_profiles_partial", "scene_profiles_running")).toBe(
      "scene_profiles_running",
    );
  });

  it("prefers active detail over interrupted progress", () => {
    expect(mergeBoundJourneyStatus("running", "scene_profiles_partial")).toBe("running");
  });
});

describe("resolveCurrentJourneyExecutionState", () => {
  it("masks stale interrupt progress when detail succeeded with result", () => {
    const state = resolveCurrentJourneyExecutionState({
      journeyRunId: 3,
      detailStatus: "succeeded",
      progressStatus: "scene_profiles_partial",
      resultExists: true,
      retryable: true,
      failureCode: "JOURNEY_INTERRUPTED",
    });
    expect(state.phase).toBe("succeeded");
    expect(state.page_view).toBe("completed");
    expect(state.show_result).toBe(true);
    expect(state.show_interrupted_view).toBe(false);
    expect(state.show_progress_card).toBe(false);
  });

  it("shows terminal failure for retryable failed journey", () => {
    const state = resolveCurrentJourneyExecutionState({
      journeyRunId: 2,
      detailStatus: "failed",
      progressStatus: "failed",
      retryable: true,
      resultExists: false,
    });
    expect(state.page_view).toBe("terminal_failed");
    expect(state.show_failure_view).toBe(true);
    expect(state.show_retry_journey).toBe(true);
    expect(state.show_interrupted_view).toBe(false);
  });

  it("shows interrupted view for recoverable partial", () => {
    const state = resolveCurrentJourneyExecutionState({
      journeyRunId: 7,
      detailStatus: "scene_profiles_partial",
      progressStatus: "scene_profiles_partial",
      retryable: true,
      resultExists: false,
    });
    expect(state.page_view).toBe("interrupted");
    expect(state.show_interrupted_view).toBe(true);
    expect(state.show_continue_analysis).toBe(true);
    expect(state.show_progress_card).toBe(false);
  });

  it("shows progress card only for active phase", () => {
    const state = resolveCurrentJourneyExecutionState({
      journeyRunId: 42,
      detailStatus: "scene_profiles_running",
      progressStatus: "scene_profiles_running",
      resultExists: false,
    });
    expect(state.page_view).toBe("active");
    expect(state.show_progress_card).toBe(true);
  });

  it("temporary fetch error maps to temporary_error page view", () => {
    const state = resolveCurrentJourneyExecutionState({
      journeyRunId: 1,
      detailStatus: null,
      progressStatus: null,
      temporaryFetchError: true,
      resultExists: false,
    });
    expect(state.page_view).toBe("temporary_error");
  });
});
