/**
 * Journey progress / result pane view priority (CHG-20260731-023 final).
 *
 * Terminal bound-journey status (succeeded/failed/cancelled) always beats
 * active progress / parent / effective_status. Progress must never mask terminal.
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
  "starting",
  "resuming",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
]);

const JOURNEY_INTERRUPTED = new Set([
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
]);

export type JourneyPageStateInput = {
  currentJourneyId?: number | null;
  responseJourneyId?: number | null;
  /** Authoritative merged status (prefer mergeBoundJourneyStatus first). */
  journeyStatus?: string | null;
  /** @deprecated Prefer merging into journeyStatus; kept for callers. */
  progressStatus?: string | null;
  parentJourneyStatus?: string | null;
  effectiveStatus?: string | null;
  errorCode?: string | null;
  retryable?: boolean | null;
  finalArtifactAvailable?: boolean | null;
  chapterComplete?: boolean | null;
  temporaryFetchError?: boolean;
  requestSequence?: number | null;
  appliedSequence?: number | null;
  responseUpdatedAt?: string | null;
  appliedUpdatedAt?: string | null;
};

function isActiveStatus(status: string | null | undefined): boolean {
  return Boolean(status && JOURNEY_ACTIVE.has(status));
}

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : null;
}

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
 * Priority (enforced): succeeded/result → failed → cancelled → active → interrupted
 * → temporary error → awaiting → unknown.
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

  // Merge with terminal-first rule (never `detail || progress` raw).
  const journeyRaw = String(input.journeyStatus || "");
  const progressRaw = String(input.progressStatus || "");
  let journey = journeyRaw;
  if (journeyRaw === "succeeded" || progressRaw === "succeeded") {
    journey = "succeeded";
  } else if (journeyRaw === "failed" || progressRaw === "failed") {
    journey = "failed";
  } else if (journeyRaw === "cancelled" || progressRaw === "cancelled") {
    journey = "cancelled";
  } else if (isActiveStatus(progressRaw)) {
    journey = progressRaw;
  } else if (isActiveStatus(journeyRaw)) {
    journey = journeyRaw;
  } else if (!journeyRaw && progressRaw) {
    journey = progressRaw;
  }

  const parent = String(input.parentJourneyStatus || "");
  const effective = String(input.effectiveStatus || "");

  // 1) succeeded / result
  if (journey === "succeeded") {
    return "completed";
  }
  if (
    (input.finalArtifactAvailable === true || input.chapterComplete === true) &&
    journey !== "failed" &&
    journey !== "cancelled" &&
    !JOURNEY_INTERRUPTED.has(journey) &&
    !isActiveStatus(journey)
  ) {
    return "completed";
  }

  // 2) failed / cancelled — BEFORE active (fixes stale active masking terminal)
  if (journey === "failed" || journey === "cancelled") {
    return "terminal_failed";
  }
  // Do not let parent/effective invent failure over bound interrupt; only when
  // bound journey status is empty/non-recoverable.
  if (
    effective === "journey_failed" &&
    !journey &&
    !JOURNEY_INTERRUPTED.has(parent)
  ) {
    return "terminal_failed";
  }

  // 3) active — bound journey only; parent/effective must NOT override terminal
  // (terminal already returned). Parent may refine only when journey missing.
  if (isActiveStatus(journey)) {
    return "active";
  }
  if (!journey && (isActiveStatus(parent) || effective === "journey_running")) {
    return "active";
  }

  // 4) interrupted
  if (JOURNEY_INTERRUPTED.has(journey)) {
    return "interrupted";
  }
  if (!journey && JOURNEY_INTERRUPTED.has(progressRaw)) {
    return "interrupted";
  }

  // 5) temporary
  if (input.temporaryFetchError) {
    return "temporary_error";
  }

  // 6) awaiting / unknown
  if (!journey && !progressRaw && !parent) {
    if (effective === "partial_complete") return "awaiting_start";
    return "unknown";
  }
  if (effective === "partial_complete") {
    return "awaiting_start";
  }
  return "unknown";
}

export function shouldPollJourneyResult(args: {
  journeyStatus?: string | null;
  parentJourneyStatus?: string | null;
  effectiveStatus?: string | null;
  sceneComplete?: boolean;
  pageView?: JourneyPageView;
}): boolean {
  if (args.pageView === "active" || args.pageView === "temporary_error") return true;
  if (args.pageView === "completed" || args.pageView === "terminal_failed") return false;
  const status = String(args.journeyStatus || "");
  if (status === "succeeded" || status === "failed" || status === "cancelled") return false;
  if (args.effectiveStatus === "journey_running") return true;
  if (isActiveStatus(args.journeyStatus) || isActiveStatus(args.parentJourneyStatus)) return true;
  if (args.sceneComplete && !args.journeyStatus) return true;
  return false;
}
