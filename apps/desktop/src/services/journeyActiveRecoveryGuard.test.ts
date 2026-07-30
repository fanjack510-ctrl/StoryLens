import { describe, expect, it } from "vitest";
import {
  isJourneyActivelyRunning,
  recoveryPlanQueryKey,
  resolveJourneyActionFlags,
  resolveShowRecoveryCard,
  shouldShowUnifiedRecoveryForJourney,
} from "./journeyActiveRecoveryGuard";
import { buildChapterAnalysisPresentationV1 } from "./chapterAnalysisPresentation";

describe("CHG-018 recovery card visibility §五–八", () => {
  it("journey_running + stale paused plan ⇒ hide recovery", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "running",
        recoveryUserStatus: "paused_recoverable",
        canResume: true,
        hasCheckpointOrRecoveryBasis: true,
      }),
    ).toBe(false);
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "reader_journey_processing",
      pageView: "active",
      journeyStatus: "running",
      canResumeJourney: true,
    });
    expect(p.is_journey_active).toBe(true);
    expect(p.show_recovery_card).toBe(false);
    expect(p.show_resume_action).toBe(false);
    expect(p.status_title).toBe("正在生成阅读旅程");
  });

  it("journey_starting + interrupted plan ⇒ hide recovery", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "starting",
        recoveryUserStatus: "paused_recoverable",
        canResume: true,
      }),
    ).toBe(false);
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "awaiting_reader_journey_start",
      journeyStatus: "starting",
    });
    expect(p.workflow_state).toBe("journey_starting");
    expect(p.show_recovery_card).toBe(false);
    expect(p.status_title).toBe("正在启动阅读旅程");
  });

  it("resuming hides resume button and recovery card", () => {
    const p = buildChapterAnalysisPresentationV1({
      chapterId: 1,
      composition: "reader_journey_processing",
      pageView: "active",
      journeyStatus: "resuming",
      canResumeJourney: true,
    });
    expect(p.is_journey_active).toBe(true);
    expect(p.show_recovery_card).toBe(false);
    expect(p.show_resume_action).toBe(false);
    expect(p.status_title).toBe("正在恢复阅读旅程");
  });

  it("current running wins over historical interrupted identity mismatch", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "interrupted",
        canResume: true,
        hasCheckpointOrRecoveryBasis: true,
        currentJourneyRunId: 10,
        planJourneyRunId: 2,
      }),
    ).toBe(false);
  });

  it("real interrupted without active task shows recovery", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "interrupted",
        canResume: true,
        hasValidWorkerLease: false,
        hasActiveTask: false,
        hasCheckpointOrRecoveryBasis: true,
        currentAnalysisRunId: 5,
        planAnalysisRunId: 5,
        currentJourneyRunId: 9,
        planJourneyRunId: 9,
        currentStatusVersion: 3,
        planStatusVersion: 3,
      }),
    ).toBe(true);
    const flags = resolveJourneyActionFlags({
      workflowState: "journey_interrupted",
      journeyStatus: "interrupted",
      canResume: true,
      showRecoveryCard: true,
    });
    expect(flags.showResumeAction).toBe(true);
    expect(flags.showStopAction).toBe(false);
  });

  it("succeeded hides recovery", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "succeeded",
        canResume: true,
      }),
    ).toBe(false);
  });

  it("status_version mismatch invalidates card", () => {
    expect(
      resolveShowRecoveryCard({
        journeyStatus: "interrupted",
        canResume: true,
        hasCheckpointOrRecoveryBasis: true,
        currentStatusVersion: 4,
        planStatusVersion: 2,
      }),
    ).toBe(false);
  });

  it("recovery plan query key includes identity fields", () => {
    expect(
      recoveryPlanQueryKey({
        analysisRunId: 7,
        journeyRunId: 11,
        confirmedRevisionId: 3,
        statusVersion: 2,
      }),
    ).toEqual(["analysis-recovery-plan", 7, 11, 3, 2]);
  });

  it("legacy helper still hides when journey active", () => {
    expect(
      shouldShowUnifiedRecoveryForJourney({
        uiState: "awaiting_reader_journey_start",
        journeyStatus: "starting",
      }),
    ).toBe(false);
    expect(isJourneyActivelyRunning("scene_profiles_running")).toBe(true);
  });
});
