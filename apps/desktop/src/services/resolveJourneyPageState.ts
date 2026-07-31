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

/** Recoverable interrupt statuses — NOT including `failed` (CHG-023 failure presentation). */
const JOURNEY_INTERRUPTED = new Set([
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
  _errorCode?: string | null,
  _retryable?: boolean | null,
): boolean {
  if (!status) return false;
  // CHG-023: `failed` is never interrupted — even when retryable / JOURNEY_INTERRUPTED.
  if (status === "failed") return false;
  if (status === "scene_profiles_partial") return true;
  if (status === "budget_blocked") return true;
  if (status === "aborted_by_limit") return true;
  return JOURNEY_INTERRUPTED.has(status);
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
 * Priority (CHG-023): succeeded/result → cancelled → failed → active → recoverable
 * interrupted → temporary error → awaiting → unknown.
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

  // Active — parent/progress can override a stale failed journey GET
  if (
    isActiveStatus(journey) ||
    isActiveStatus(progress) ||
    isActiveStatus(parent) ||
    effective === "journey_running"
  ) {
    return "active";
  }

  // Artifact / chapter complete: wins over stale failed GET (9.2/9.7), but not over
  // a still-recoverable bound interrupt (CHG-015 sibling chapter_complete).
  if (input.finalArtifactAvailable === true || input.chapterComplete === true) {
    if (
      journey === "scene_profiles_partial" ||
      journey === "budget_blocked" ||
      journey === "aborted_by_limit"
    ) {
      return "interrupted";
    }
    return "completed";
  }

  // CHG-023: failed beats interrupted / stale recovery_recommended / retryable rewrite.
  // Must follow active so a live progress/parent still wins over a stale failed GET.
  if (journey === "failed" || progress === "failed") {
    return "terminal_failed";
  }
  if (
    effective === "journey_failed" &&
    journey !== "scene_profiles_partial" &&
    journey !== "budget_blocked" &&
    journey !== "aborted_by_limit"
  ) {
    return "terminal_failed";
  }

  // Bound / selected journey still recoverable. Must win over parent chapter_complete
  // from a newer sibling auto-journey (CHG-015 Manual Gate recoverable split).
  // Never classify status=failed as interrupted (retryable only gates retry CTA).
  const boundRecoverableInterrupted =
    journey === "scene_profiles_partial" ||
    journey === "budget_blocked" ||
    journey === "aborted_by_limit" ||
    // Progress may refine only while journey GET is missing / non-terminal.
    (!journey &&
      (progress === "scene_profiles_partial" ||
        progress === "budget_blocked" ||
        progress === "aborted_by_limit"));

  if (boundRecoverableInterrupted) {
    return "interrupted";
  }

  if (journey === "succeeded" && effective === "completed") {
    return "completed";
  }

  // Interrupted / recoverable (partial / budget) — not failed
  if (
    isInterruptedStatus(journey, input.errorCode, input.retryable) ||
    (!journey && isInterruptedStatus(progress, input.errorCode, input.retryable)) ||
    isInterruptedStatus(parent, input.errorCode, input.retryable) ||
    journey === "scene_profiles_partial" ||
    (!journey && progress === "scene_profiles_partial") ||
    journey === "budget_blocked"
  ) {
    return "interrupted";
  }

  // Temporary connection error — never “重新生成”
  if (input.temporaryFetchError) {
    return "temporary_error";
  }

  // Awaiting start / unknown
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
