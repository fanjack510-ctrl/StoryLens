import { describe, expect, it } from "vitest";
import { buildChapterAnalysisPresentationV1 } from "./chapterAnalysisPresentation";
import { resolveShowRecoveryCard } from "./journeyActiveRecoveryGuard";
import { resolveJourneyPageState } from "./resolveJourneyPageState";

describe("CHG-023 recovery UI sync", () => {
  it("A: succeeded + stale recovery plan → result, no recovery card, no continue", () => {
    const pageView = resolveJourneyPageState({
      currentJourneyId: 3,
      responseJourneyId: 3,
      journeyStatus: "succeeded",
      progressStatus: "scene_profiles_partial",
      errorCode: "JOURNEY_INTERRUPTED",
      retryable: true,
      finalArtifactAvailable: true,
      chapterComplete: true,
    });
    expect(pageView).toBe("completed");

    const presentation = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      analysisRunId: 6,
      journeyRunId: 3,
      composition: "succeeded",
      pageView,
      journeyStatus: "succeeded",
      chapterComplete: true,
      canResumeJourney: true,
      hasCheckpointOrRecoveryBasis: true,
    });
    expect(presentation.workflow_state).toBe("journey_succeeded");
    expect(presentation.show_recovery_card).toBe(false);
    expect(presentation.show_resume_action).toBe(false);
    expect(presentation.can_resume).toBe(false);
    expect(presentation.primary_action).toBe("view_results");
  });

  it("E: result route inputs resolve completed without interrupted", () => {
    expect(
      resolveJourneyPageState({
        journeyStatus: "succeeded",
        finalArtifactAvailable: true,
        errorCode: "JOURNEY_INTERRUPTED",
      }),
    ).toBe("completed");
  });

  it("H: recovery card requires can_resume and hides on succeeded", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "succeeded",
        canResume: true,
        hasCheckpointOrRecoveryBasis: true,
        recoveryUserStatus: "paused_recoverable",
      }),
    ).toBe(false);
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "scene_profiles_partial",
        canResume: true,
        hasCheckpointOrRecoveryBasis: true,
        workflowState: "journey_interrupted",
      }),
    ).toBe(true);
  });
});
