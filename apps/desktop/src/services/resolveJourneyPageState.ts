/**
 * Journey progress / result pane view priority (CHG-20260727-020).
 *
 * Prevents stale failed GET /reader-journey responses from covering an active
 * or completed journey that AnalysisRun composition already reflects.
 */

export type JourneyPageView =
  | "completed"
  | "active"
  | "interrupted"
  | "terminal_failed"
  | "temporary_error"
  | "awaiting_start"
  | "unknown";

const JOURNEY_ACTIVE = new Set([
  "queued",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
]);

const JOURNEY_INTERRUPTED = new Set([
  "failed",
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
]);

export type JourneyPageStateInput = {
  /** Bound / expected journey id for this page (may be null before first fetch). */
  currentJourneyId?: number | null;
  /** Journey id on the response being applied. */
  responseJourneyId?: number | null;
  /** Status from GET /reader-journey (may be stale). */
  journeyStatus?: string | null;
  /** Status from GET .../progress (may be fresher while running). */
  progressStatus?: string | null;
  /** Parent AnalysisRun.journey_status / effective_status projection. */
  parentJourneyStatus?: string | null;
  effectiveStatus?: string | null;
  errorCode?: string | null;
  retryable?: boolean | null;
  finalArtifactAvailable?: boolean | null;
  chapterComplete?: boolean | null;
  /** True when GET /reader-journey failed as transport/network (not business failed). */
  temporaryFetchError?: boolean;
  /** Monotonic request sequence for the response under consideration. */
  requestSequence?: number | null;
  /** Last applied sequence — ignore older responses when provided. */
  appliedSequence?: number | null;
  /** ISO timestamps — ignore older updatedAt when both present. */
  responseUpdatedAt?: string | null;
  appliedUpdatedAt?: string | null;
};

function isActiveStatus(status: string | null | undefined): boolean {
  return Boolean(status && JOURNEY_ACTIVE.has(status));
}

function isInterruptedStatus(
  status: string | null | undefined,
  errorCode?: string | null,
  retryable?: boolean | null,
): boolean {
  if (!status) return false;
  // errorCode alone must not flip a succeeded/running row; require matching status.
  if (status === "scene_profiles_partial") return true;
  if (status === "budget_blocked") return true;
  if (errorCode === "JOURNEY_INTERRUPTED" && JOURNEY_INTERRUPTED.has(status)) return true;
  if (JOURNEY_INTERRUPTED.has(status) && retryable === true) return true;
  return false;
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

/** Returns true when the candidate response should be ignored as stale. */
export function isStaleJourneyResponse(input: {
  responseJourneyId?: number | null;
  currentJourneyId?: number | null;
  requestSequence?: number | null;
  appliedSequence?: number | null;
  responseUpdatedAt?: string | null;
  appliedUpdatedAt?: string | null;
}): boolean {
  if (
    input.currentJourneyId != null &&
    input.responseJourneyId != null &&
    Number(input.currentJourneyId) !== Number(input.responseJourneyId)
  ) {
    return true;
  }
  if (
    input.appliedSequence != null &&
    input.requestSequence != null &&
    input.requestSequence < input.appliedSequence
  ) {
    return true;
  }
  const appliedMs = parseTime(input.appliedUpdatedAt);
  const responseMs = parseTime(input.responseUpdatedAt);
  if (appliedMs != null && responseMs != null && responseMs < appliedMs) {
    return true;
  }
  return false;
}

/**
 * Resolve the Journey tab main-pane view.
 * Priority (CHG-023): succeeded/result → cancelled → active → recoverable interrupted
 * → terminal failed → temporary error → awaiting → unknown.
 * Returns null when the candidate response is stale and must not replace the current view.
 */
export function resolveJourneyPageState(input: JourneyPageStateInput): JourneyPageView | null {
  if (
    isStaleJourneyResponse({
      responseJourneyId: input.responseJourneyId,
      currentJourneyId: input.currentJourneyId,
      requestSequence: input.requestSequence,
      appliedSequence: input.appliedSequence,
      responseUpdatedAt: input.responseUpdatedAt,
      appliedUpdatedAt: input.appliedUpdatedAt,
    })
  ) {
    return null;
  }

  const journey = String(input.journeyStatus || "");
  const progress = String(input.progressStatus || "");
  const parent = String(input.parentJourneyStatus || "");
  const effective = String(input.effectiveStatus || "");

  // CHG-023: bound journey succeeded / result exists always beats stale recovery signals
  // (cached progressStatus, JOURNEY_INTERRUPTED errorCode, paused recovery plan).
  if (journey === "succeeded") {
    return "completed";
  }
  if (
    (input.finalArtifactAvailable === true || input.chapterComplete === true) &&
    !JOURNEY_INTERRUPTED.has(journey) &&
    journey !== "scene_profiles_partial" &&
    journey !== "budget_blocked" &&
    journey !== "failed"
  ) {
    return "completed";
  }

  // Active — parent/progress can override a stale failed journey GET
  if (
    isActiveStatus(journey) ||
    isActiveStatus(progress) ||
    isActiveStatus(parent) ||
    effective === "journey_running"
  ) {
    return "active";
  }

  // Bound / selected journey still recoverable. Must win over parent chapter_complete
  // from a newer sibling auto-journey (CHG-015 Manual Gate recoverable split).
  // Only the bound journey row (not stale progress/error alone after succeed) may interrupt.
  const boundRecoverableInterrupted =
    journey === "scene_profiles_partial" ||
    journey === "budget_blocked" ||
    (journey === "failed" &&
      (input.errorCode === "JOURNEY_INTERRUPTED" || input.retryable === true)) ||
    (JOURNEY_INTERRUPTED.has(journey) && input.retryable === true) ||
    // Progress may refine only while journey GET is missing or still non-terminal.
    ((!journey || journey === "failed") &&
      (progress === "scene_profiles_partial" ||
        progress === "budget_blocked" ||
        (JOURNEY_INTERRUPTED.has(progress) && input.retryable === true)));

  if (boundRecoverableInterrupted) {
    return "interrupted";
  }

  // Completed + final artifact — overrides stale failed fields on the same journey
  if (input.finalArtifactAvailable === true || input.chapterComplete === true) {
    // Sibling chapter_complete must not hide a still-recoverable bound journey (CHG-015).
    if (
      journey === "scene_profiles_partial" ||
      journey === "budget_blocked" ||
      (JOURNEY_INTERRUPTED.has(journey) && input.retryable === true)
    ) {
      return "interrupted";
    }
    return "completed";
  }
  if (journey === "succeeded" && effective === "completed") {
    return "completed";
  }

  // Interrupted / recoverable (including retryable failed / JOURNEY_INTERRUPTED)
  if (
    isInterruptedStatus(journey, input.errorCode, input.retryable) ||
    ((!journey || journey === "failed") &&
      isInterruptedStatus(progress, input.errorCode, input.retryable)) ||
    isInterruptedStatus(parent, input.errorCode, input.retryable) ||
    journey === "scene_profiles_partial" ||
    ((!journey || journey === "failed") && progress === "scene_profiles_partial") ||
    journey === "budget_blocked" ||
    (effective === "journey_failed" && input.retryable !== false && journey !== "succeeded")
  ) {
    return "interrupted";
  }

  // 4. Terminal failed — only when current journey is failed, no active signal, no artifact
  if (
    (journey === "failed" || progress === "failed") &&
    !isActiveStatus(parent) &&
    effective !== "journey_running"
  ) {
    return "terminal_failed";
  }

  // 5. Temporary connection error — never “重新生成”
  if (input.temporaryFetchError) {
    return "temporary_error";
  }

  // 6. Awaiting start / unknown
  if (!journey && !progress && !parent) {
    if (effective === "partial_complete") return "awaiting_start";
    return "unknown";
  }
  if (JOURNEY_INTERRUPTED.has(journey) || effective === "partial_complete") {
    return "awaiting_start";
  }
  return "unknown";
}

/** Whether the journey GET query should keep polling. */
export function shouldPollJourneyResult(args: {
  journeyStatus?: string | null;
  parentJourneyStatus?: string | null;
  effectiveStatus?: string | null;
  sceneComplete?: boolean;
  pageView?: JourneyPageView;
}): boolean {
  if (args.pageView === "active" || args.pageView === "temporary_error") return true;
  if (args.effectiveStatus === "journey_running") return true;
  if (isActiveStatus(args.journeyStatus) || isActiveStatus(args.parentJourneyStatus)) return true;
  if (args.sceneComplete && !args.journeyStatus) return true;
  return false;
}
