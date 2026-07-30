/**
 * CHG-20260730-018 — Journey statuses that mean generation is already active.
 * Stale Recovery Card / recover CTA must not surface while these hold.
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

export function isJourneyActivelyRunning(
  status: string | null | undefined,
): boolean {
  if (!status) return false;
  return JOURNEY_ACTIVE_STATUSES.has(String(status).toLowerCase());
}

/** Whether ordinary UI should host the unified recovery card. */
export function shouldShowUnifiedRecoveryForJourney(args: {
  uiState: string | undefined | null;
  journeyStatus?: string | null;
  recoveryUserStatus?: string | null;
  journeyPageActive?: boolean;
}): boolean {
  if (args.journeyPageActive) return false;
  if (isJourneyActivelyRunning(args.journeyStatus)) return false;
  if (args.recoveryUserStatus === "running" || args.recoveryUserStatus === "succeeded") {
    return false;
  }
  return (
    args.uiState === "awaiting_budget_adjustment" ||
    args.uiState === "provider_recovery" ||
    args.uiState === "awaiting_reader_journey_start" ||
    args.uiState === "partial" ||
    args.uiState === "failed" ||
    args.uiState === "aborted_by_limit"
  );
}
