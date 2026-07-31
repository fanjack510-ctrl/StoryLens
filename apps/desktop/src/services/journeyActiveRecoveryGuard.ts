/**
 * CHG-20260730-018 — Recovery Card visibility + active-journey presentation flags.
 *
 * Ordinary UI must compute showRecoveryCard here; components must not re-enable
 * a paused card from a stale Recovery Plan alone while the current journey is active.
 */

export const JOURNEY_ACTIVE_STATUSES = new Set([
  "journey_starting",
  "journey_running",
  "resuming",
  "queued",
  "pending",
  "starting",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
  "reader_journey_processing",
]);

export const JOURNEY_RECOVERABLE_STATUSES = new Set([
  "interrupted",
  "paused",
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
  "recoverable_failed",
  "failed",
]);

export type RecoveryCardVisibilityInput = {
  /** Selected / bound journey status for the current task. */
  journeyStatus?: string | null;
  /** Parent AnalysisRun workflow / composition hints. */
  workflowState?: string | null;
  uiState?: string | null;
  journeyPageActive?: boolean;
  canResume?: boolean | null;
  hasValidWorkerLease?: boolean | null;
  hasActiveTask?: boolean | null;
  hasCheckpointOrRecoveryBasis?: boolean | null;
  /** Plan binding must match current shell identity. */
  currentAnalysisRunId?: number | null;
  planAnalysisRunId?: number | null;
  currentJourneyRunId?: number | null;
  planJourneyRunId?: number | null;
  currentConfirmedRevisionId?: number | null;
  planConfirmedRevisionId?: number | null;
  currentStatusVersion?: number | null;
  planStatusVersion?: number | null;
  recoveryUserStatus?: string | null;
};

export function isJourneyActivelyRunning(
  status: string | null | undefined,
): boolean {
  if (!status) return false;
  return JOURNEY_ACTIVE_STATUSES.has(String(status).toLowerCase());
}

export function isJourneyActiveWorkflow(
  workflowState: string | null | undefined,
  journeyStatus?: string | null,
): boolean {
  const wf = String(workflowState || "").toLowerCase();
  if (
    wf === "journey_starting" ||
    wf === "journey_running" ||
    wf === "resuming" ||
    wf === "starting" ||
    wf === "queued"
  ) {
    return true;
  }
  return isJourneyActivelyRunning(journeyStatus);
}

/**
 * §五: Recovery Card only when ALL conditions hold.
 * Any miss ⇒ false.
 */
export function resolveShowRecoveryCard(args: RecoveryCardVisibilityInput): boolean {
  if (args.journeyPageActive) return false;
  if (isJourneyActiveWorkflow(args.workflowState, args.journeyStatus)) return false;
  if (args.hasValidWorkerLease === true) return false;
  if (args.hasActiveTask === true) return false;

  const status = String(args.journeyStatus || "").toLowerCase();
  // CHG-023: succeeded / cancelled / failed never show recovery over terminal journey.
  if (
    status === "succeeded" ||
    status === "cancelled" ||
    status === "failed" ||
    args.workflowState === "journey_succeeded" ||
    args.workflowState === "journey_failed" ||
    args.recoveryUserStatus === "succeeded"
  ) {
    return false;
  }
  const recoverableStatus =
    JOURNEY_RECOVERABLE_STATUSES.has(status) ||
    args.uiState === "awaiting_budget_adjustment" ||
    args.uiState === "provider_recovery" ||
    args.uiState === "partial" ||
    args.uiState === "failed" ||
    args.uiState === "aborted_by_limit" ||
    args.uiState === "awaiting_reader_journey_start";

  if (!recoverableStatus) return false;
  if (args.canResume !== true && status !== "paused" && args.uiState !== "awaiting_budget_adjustment") {
    // Interrupted / failed need can_resume; budget pause may use uiState alone.
    if (
      status === "interrupted" ||
      status === "scene_profiles_partial" ||
      status === "failed" ||
      status === "recoverable_failed"
    ) {
      return false;
    }
  }
  if (args.hasCheckpointOrRecoveryBasis === false) return false;

  if (
    args.currentAnalysisRunId != null &&
    args.planAnalysisRunId != null &&
    Number(args.currentAnalysisRunId) !== Number(args.planAnalysisRunId)
  ) {
    return false;
  }
  if (
    args.currentJourneyRunId != null &&
    args.planJourneyRunId != null &&
    Number(args.currentJourneyRunId) !== Number(args.planJourneyRunId)
  ) {
    return false;
  }
  if (
    args.currentConfirmedRevisionId != null &&
    args.planConfirmedRevisionId != null &&
    Number(args.currentConfirmedRevisionId) !== Number(args.planConfirmedRevisionId)
  ) {
    return false;
  }
  if (
    args.currentStatusVersion != null &&
    args.planStatusVersion != null &&
    Number(args.currentStatusVersion) !== Number(args.planStatusVersion)
  ) {
    return false;
  }

  if (args.recoveryUserStatus === "running" || args.recoveryUserStatus === "succeeded") {
    return false;
  }

  return true;
}

export function resolveJourneyActionFlags(args: {
  workflowState?: string | null;
  journeyStatus?: string | null;
  canResume?: boolean | null;
  showRecoveryCard?: boolean;
}): {
  isJourneyActive: boolean;
  showRecoveryCard: boolean;
  showResumeAction: boolean;
  showStopAction: boolean;
} {
  const isJourneyActive = isJourneyActiveWorkflow(args.workflowState, args.journeyStatus);
  const showRecoveryCard = args.showRecoveryCard === true && !isJourneyActive;
  return {
    isJourneyActive,
    showRecoveryCard,
    showResumeAction: !isJourneyActive && showRecoveryCard && args.canResume === true,
    showStopAction: isJourneyActive,
  };
}

/** @deprecated Prefer resolveShowRecoveryCard — kept for ProgressPanel uiState gate. */
export function shouldShowUnifiedRecoveryForJourney(args: {
  uiState: string | undefined | null;
  journeyStatus?: string | null;
  recoveryUserStatus?: string | null;
  journeyPageActive?: boolean;
  workflowState?: string | null;
  canResume?: boolean | null;
}): boolean {
  return resolveShowRecoveryCard({
    uiState: args.uiState,
    journeyStatus: args.journeyStatus,
    recoveryUserStatus: args.recoveryUserStatus,
    journeyPageActive: args.journeyPageActive,
    workflowState: args.workflowState,
    canResume: args.canResume ?? true,
    hasCheckpointOrRecoveryBasis: true,
  });
}

/** React Query key — must include identity fields (§七). Never chapter_id alone. */
export function recoveryPlanQueryKey(args: {
  analysisRunId: number;
  journeyRunId?: number | null;
  confirmedRevisionId?: number | null;
  statusVersion?: number | null;
}): readonly unknown[] {
  return [
    "analysis-recovery-plan",
    args.analysisRunId,
    args.journeyRunId ?? null,
    args.confirmedRevisionId ?? null,
    args.statusVersion ?? null,
  ] as const;
}
