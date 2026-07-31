import { describe, expect, it } from "vitest";
import {
  isStaleJourneyResponse,
  resolveJourneyPageState,
  shouldPollJourneyResult,
} from "./resolveJourneyPageState";

describe("isStaleJourneyResponse", () => {
  it("rejects responses for a different journey id", () => {
    expect(
      isStaleJourneyResponse({
        currentJourneyId: 3,
        responseJourneyId: 1,
      }),
    ).toBe(true);
  });

  it("rejects older request sequences", () => {
    expect(
      isStaleJourneyResponse({
        requestSequence: 2,
        appliedSequence: 5,
      }),
    ).toBe(true);
  });

  it("rejects older updatedAt", () => {
    expect(
      isStaleJourneyResponse({
        responseUpdatedAt: "2026-07-27T01:00:00Z",
        appliedUpdatedAt: "2026-07-27T02:00:00Z",
      }),
    ).toBe(true);
  });

  it("accepts fresher responses", () => {
    expect(
      isStaleJourneyResponse({
        currentJourneyId: 3,
        responseJourneyId: 3,
        requestSequence: 6,
        appliedSequence: 5,
        responseUpdatedAt: "2026-07-27T03:00:00Z",
        appliedUpdatedAt: "2026-07-27T02:00:00Z",
      }),
    ).toBe(false);
  });
});

describe("resolveJourneyPageState", () => {
  it("9.1 active overrides old failure", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        progressStatus: "scene_profiles_running",
        effectiveStatus: "journey_running",
        requestSequence: 2,
        appliedSequence: 1,
      }),
    ).toBe("active");
  });

  it("9.2 completed overrides old failure", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        finalArtifactAvailable: true,
        chapterComplete: true,
        requestSequence: 3,
        appliedSequence: 2,
      }),
    ).toBe("completed");
  });

  it("9.3 out-of-order failed response returns null so UI keeps running", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        requestSequence: 4,
        appliedSequence: 7,
      }),
    ).toBeNull();
  });

  it("9.4 old attempt failed does not override current journey running", () => {
    expect(
      resolveJourneyPageState({
        currentJourneyId: 2,
        responseJourneyId: 1,
        journeyStatus: "failed",
      }),
    ).toBeNull();
    expect(
      resolveJourneyPageState({
        currentJourneyId: 2,
        responseJourneyId: 2,
        journeyStatus: "scene_profiles_running",
      }),
    ).toBe("active");
  });

  it("9.5 temporary API error is not regenerate failure", () => {
    expect(
      resolveJourneyPageState({
        temporaryFetchError: true,
      }),
    ).toBe("temporary_error");
    expect(
      resolveJourneyPageState({
        temporaryFetchError: true,
        journeyStatus: "failed",
        retryable: false,
      }),
    ).toBe("terminal_failed");
  });

  it("9.6 terminal failure when current journey failed without artifact", () => {
    expect(
      resolveJourneyPageState({
        currentJourneyId: 3,
        responseJourneyId: 3,
        journeyStatus: "failed",
        retryable: false,
        finalArtifactAvailable: false,
      }),
    ).toBe("terminal_failed");
  });

  it("9.7 final artifact wins even with stale error fields", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        errorCode: "SOME_OLD_ERROR",
        finalArtifactAvailable: true,
      }),
    ).toBe("completed");
  });

  it("maps retryable / interrupted failures away from terminal failed", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        retryable: true,
      }),
    ).toBe("interrupted");
    expect(
      resolveJourneyPageState({
        journeyStatus: "scene_profiles_partial",
      }),
    ).toBe("interrupted");
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        errorCode: "JOURNEY_INTERRUPTED",
      }),
    ).toBe("interrupted");
  });

  it("bound recoverable interrupted wins over sibling chapter_complete", () => {
    expect(
      resolveJourneyPageState({
        currentJourneyId: 2,
        responseJourneyId: 2,
        journeyStatus: "scene_profiles_partial",
        errorCode: "JOURNEY_INTERRUPTED",
        retryable: true,
        chapterComplete: true,
        finalArtifactAvailable: true,
        parentJourneyStatus: "succeeded",
        effectiveStatus: "completed",
      }),
    ).toBe("interrupted");
  });

  it("succeeded journey still completes even when parent chapter_complete", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "succeeded",
        chapterComplete: true,
        finalArtifactAvailable: true,
      }),
    ).toBe("completed");
  });

  it("CHG-023: succeeded + result beats stale interrupted progress/errorCode", () => {
    expect(
      resolveJourneyPageState({
        currentJourneyId: 3,
        responseJourneyId: 3,
        journeyStatus: "succeeded",
        progressStatus: "scene_profiles_partial",
        errorCode: "JOURNEY_INTERRUPTED",
        retryable: true,
        finalArtifactAvailable: true,
        chapterComplete: true,
        parentJourneyStatus: "failed",
        effectiveStatus: "journey_failed",
      }),
    ).toBe("completed");
  });

  it("CHG-023: stale JOURNEY_INTERRUPTED errorCode alone does not interrupt succeeded", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "succeeded",
        errorCode: "JOURNEY_INTERRUPTED",
        retryable: true,
        finalArtifactAvailable: true,
      }),
    ).toBe("completed");
  });

  it("parent journey_running overrides stale failed GET", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "failed",
        parentJourneyStatus: "scene_profiles_running",
        effectiveStatus: "journey_running",
      }),
    ).toBe("active");
  });
});

describe("shouldPollJourneyResult", () => {
  it("keeps polling for active and temporary error views", () => {
    expect(shouldPollJourneyResult({ pageView: "active" })).toBe(true);
    expect(shouldPollJourneyResult({ pageView: "temporary_error" })).toBe(true);
    expect(shouldPollJourneyResult({ pageView: "terminal_failed" })).toBe(false);
    expect(
      shouldPollJourneyResult({
        effectiveStatus: "journey_running",
        journeyStatus: "failed",
      }),
    ).toBe(true);
  });
});
