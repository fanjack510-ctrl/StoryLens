/**
 * Composite chapter AnalysisRun + Reader Journey lifecycle (CHG-20260727-019).
 *
 * Parent `succeeded` alone must not drive "查看结果" while Journey is active
 * or interrupted without a final artifact.
 */

export type CompositeLifecyclePhase =
  | "none"
  | "awaiting_user"
  | "active"
  | "interrupted"
  | "completed"
  | "failed"
  | "cancelled";

const JOURNEY_ACTIVE = new Set([
  "starting",
  "queued",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
]);

const JOURNEY_RECOVERABLE = new Set([
  "failed",
  "scene_profiles_partial",
  "budget_blocked",
  "aborted_by_limit",
]);

const PARENT_AWAITING = new Set(["awaiting_boundary_review", "boundary_review_required"]);

const PARENT_ACTIVE = new Set([
  "pending",
  "preparing",
  "queued",
  "running",
  "analyzing",
  "materializing",
  "synthesizing",
  "paused",
  "boundary_candidates_running",
  "boundary_confirmed",
  "boundary_confirmed_budget_blocked",
  "scene_analysis_running",
  "scene_analysis_partial",
  "boundary_candidates_partial",
  "awaiting_provider_recovery",
  "aborted_by_limit",
]);

const PARENT_COMPLETED = new Set(["completed", "succeeded"]);
const PARENT_FAILED = new Set(["failed", "failed_provider", "failed_structural"]);
const PARENT_CANCELLED = new Set(["cancelled", "review_cancelled", "review_expired"]);

export type CompositeRunLifecycleInput = {
  parentStatus?: string | null;
  journeyStatus?: string | null;
  journeyResultAvailable?: boolean | null;
  journeyRetryable?: boolean | null;
  journeyErrorCode?: string | null;
  effectiveStatus?: string | null;
  chapterComplete?: boolean | null;
};

export function resolveCompositeRunLifecycle(
  input: CompositeRunLifecycleInput,
): CompositeLifecyclePhase {
  const parent = String(input.parentStatus || "").toLowerCase();
  const journey = String(input.journeyStatus || "").toLowerCase();
  const effective = String(input.effectiveStatus || "").toLowerCase();
  const resultAvailable = Boolean(input.journeyResultAvailable);
  const retryable =
    input.journeyRetryable === true ||
    input.journeyErrorCode === "JOURNEY_INTERRUPTED" ||
    journey === "scene_profiles_partial";

  // CHG-013: live journey active (incl. starting) before stale awaiting confirmation.
  if (JOURNEY_ACTIVE.has(journey) || effective === "journey_running") {
    return "active";
  }

  if (effective === "awaiting_scene_boundary_confirmation") {
    return "awaiting_user";
  }

  // 2. Journey interrupted / failed retryable
  if (
    JOURNEY_RECOVERABLE.has(journey) ||
    effective === "journey_failed" ||
    (journey === "failed" && retryable)
  ) {
    return "interrupted";
  }

  // 3. Journey completed + final artifact
  if (journey === "succeeded" && resultAvailable) {
    return "completed";
  }
  if (journey === "succeeded" && !resultAvailable) {
    // Succeeded without artifact must not advertise results.
    return "interrupted";
  }
  if (effective === "completed" || input.chapterComplete === true) {
    return "completed";
  }

  if (!parent) return "none";
  if (PARENT_CANCELLED.has(parent)) return "cancelled";
  if (PARENT_FAILED.has(parent) || parent.startsWith("failed")) return "failed";
  if (PARENT_AWAITING.has(parent)) return "awaiting_user";

  // 4. Parent active
  if (PARENT_ACTIVE.has(parent) || effective === "partial_complete") {
    // partial_complete = scenes done, journey not started → not "completed"
    if (effective === "partial_complete") return "active";
    return "active";
  }

  // 5. Parent completed (no journey row / scene-only)
  if (PARENT_COMPLETED.has(parent)) {
    return "completed";
  }

  return "active";
}

export function compositeLifecycleStatusLabel(phase: CompositeLifecyclePhase): string | null {
  switch (phase) {
    case "active":
      return null; // caller may specialize (journey vs scene)
    case "interrupted":
      return "阅读旅程已中断";
    case "completed":
      return "已完成";
    default:
      return null;
  }
}
