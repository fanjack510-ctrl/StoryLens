/**
 * CHG-20260731-023 final: single CurrentJourneyExecutionState.
 *
 * Bound journey detail is the authority for terminal page phase.
 * Progress supplies counts/stage only — never overrides terminal with non-terminal.
 * Local click-pending must NOT be passed here as page truth.
 */

export type JourneyExecutionPhase =
  | "succeeded"
  | "failed"
  | "cancelled"
  | "running"
  | "interrupted"
  | "waiting"
  | "unknown";

export type CurrentJourneyExecutionState = {
  journey_run_id: number | null;
  analysis_run_id: number | null;
  journey_status: string | null;
  progress_status: string | null;
  current_stage: string | null;
  completed_scene_count: number | null;
  total_scene_count: number | null;
  result_exists: boolean;
  failure_code: string | null;
  retryable: boolean;
  phase: JourneyExecutionPhase;
  page_view:
    | "completed"
    | "terminal_failed"
    | "interrupted"
    | "active"
    | "awaiting_start"
    | "temporary_error"
    | "unknown";
  show_progress_card: boolean;
  show_failure_view: boolean;
  show_result: boolean;
  show_interrupted_view: boolean;
  show_continue_analysis: boolean;
  show_retry_journey: boolean;
};

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const ACTIVE = new Set([
  "queued",
  "starting",
  "resuming",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
]);
const INTERRUPTED = new Set([
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
]);

/**
 * Merge detail + progress for the SAME journeyRunId.
 * Terminal from either source wins; non-terminal never masks terminal.
 */
export function mergeBoundJourneyStatus(
  detailStatus: string | null | undefined,
  progressStatus: string | null | undefined,
): string | null {
  const detail = detailStatus ? String(detailStatus) : "";
  const progress = progressStatus ? String(progressStatus) : "";
  if (TERMINAL.has(detail)) return detail;
  if (TERMINAL.has(progress)) return progress;
  if (ACTIVE.has(progress)) return progress;
  if (ACTIVE.has(detail)) return detail;
  if (INTERRUPTED.has(detail)) return detail;
  if (INTERRUPTED.has(progress)) return progress;
  return detail || progress || null;
}

/**
 * Priority:
 * succeeded (+ result preferred) → failed → cancelled → running → interrupted → waiting → unknown
 */
export function resolveCurrentJourneyExecutionState(input: {
  journeyRunId?: number | null;
  analysisRunId?: number | null;
  detailStatus?: string | null;
  progressStatus?: string | null;
  currentStage?: string | null;
  completedSceneCount?: number | null;
  totalSceneCount?: number | null;
  resultExists?: boolean;
  failureCode?: string | null;
  retryable?: boolean | null;
  temporaryFetchError?: boolean;
}): CurrentJourneyExecutionState {
  const resultExists = Boolean(input.resultExists);
  const merged = mergeBoundJourneyStatus(input.detailStatus, input.progressStatus);

  let phase: JourneyExecutionPhase;
  if (merged === "succeeded" || (resultExists && merged !== "failed" && merged !== "cancelled" && !ACTIVE.has(merged || "") && !INTERRUPTED.has(merged || ""))) {
    // Result present without interrupt/active/fail → succeeded
    if (merged === "failed") {
      phase = "failed";
    } else if (merged === "cancelled") {
      phase = "cancelled";
    } else if (merged === "succeeded" || resultExists) {
      phase = "succeeded";
    } else {
      phase = "unknown";
    }
  } else if (merged === "failed") {
    phase = "failed";
  } else if (merged === "cancelled") {
    phase = "cancelled";
  } else if (ACTIVE.has(merged || "")) {
    phase = "running";
  } else if (INTERRUPTED.has(merged || "")) {
    phase = "interrupted";
  } else if (input.temporaryFetchError) {
    phase = "waiting";
  } else if (!merged) {
    phase = resultExists ? "succeeded" : "unknown";
  } else {
    phase = "unknown";
  }

  // Hard overrides: explicit terminal status always wins (including failed over stale result).
  if (merged === "cancelled") phase = "cancelled";
  else if (merged === "failed") phase = "failed";
  else if (merged === "succeeded") phase = "succeeded";
  else if (resultExists && !ACTIVE.has(merged || "") && !INTERRUPTED.has(merged || "")) {
    phase = "succeeded";
  }
  const page_view =
    phase === "succeeded"
      ? "completed"
      : phase === "failed" || phase === "cancelled"
        ? "terminal_failed"
        : phase === "running"
          ? "active"
          : phase === "interrupted"
            ? "interrupted"
            : phase === "waiting"
              ? "temporary_error"
              : "unknown";

  const show_progress_card = phase === "running";
  const show_failure_view = phase === "failed" || phase === "cancelled";
  const show_result = phase === "succeeded";
  const show_interrupted_view = phase === "interrupted";
  const retryable = Boolean(input.retryable);

  return {
    journey_run_id: input.journeyRunId ?? null,
    analysis_run_id: input.analysisRunId ?? null,
    journey_status: merged,
    progress_status: input.progressStatus ?? null,
    current_stage: input.currentStage ?? null,
    completed_scene_count: input.completedSceneCount ?? null,
    total_scene_count: input.totalSceneCount ?? null,
    result_exists: resultExists,
    failure_code: input.failureCode ?? null,
    retryable,
    phase,
    page_view,
    show_progress_card,
    show_failure_view,
    show_result,
    show_interrupted_view,
    show_continue_analysis: show_interrupted_view && retryable,
    show_retry_journey: phase === "failed" && retryable,
  };
}
