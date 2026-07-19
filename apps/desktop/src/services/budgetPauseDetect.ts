import type { Run } from "../types";
import { isBudgetReservationCode, type BudgetGapView } from "./budgetErrorCopy";

/** True when the run is paused waiting for budget / request-limit adjustment. */
export function isBudgetPauseRun(run: Run | null | undefined): boolean {
  if (!run) return false;
  if (run.status === "boundary_confirmed_budget_blocked") return true;
  if (run.failed_stage === "scene_analysis_budget") return true;
  if (isBudgetReservationCode(run.error_code) || isBudgetReservationCode(run.root_error_code)) {
    return true;
  }
  if (
    run.status === "aborted_by_limit" &&
    (run.exceeded_dimensions?.length || run.budget_required)
  ) {
    return true;
  }
  return false;
}

export function budgetGapFromRun(run: Run): BudgetGapView {
  const required = run.budget_required || {};
  const remaining = run.budget_remaining || {};
  const dimensions = (run.exceeded_dimensions || []).filter((d): d is BudgetGapView["dimensions"][number] =>
    d === "requests" || d === "tokens" || d === "estimated_cost",
  );
  const dims =
    dimensions.length > 0
      ? dimensions
      : typeof required.requests === "number" &&
          typeof remaining.requests === "number" &&
          required.requests > remaining.requests
        ? (["requests"] as const)
        : (["requests"] as const);
  const shortfall = {
    requests:
      typeof required.requests === "number" && typeof remaining.requests === "number"
        ? Math.max(0, required.requests - remaining.requests)
        : undefined,
    tokens:
      typeof required.tokens === "number" && typeof remaining.tokens === "number"
        ? Math.max(0, required.tokens - remaining.tokens)
        : undefined,
    estimated_cost:
      typeof required.estimated_cost === "number" &&
      typeof remaining.estimated_cost === "number"
        ? Math.max(0, required.estimated_cost - remaining.estimated_cost)
        : undefined,
  };
  return {
    dimensions: [...dims],
    required,
    remaining,
    shortfall,
    run_id: run.id,
  };
}

export function budgetPauseStorageKey(runId: number): string {
  return `storylens.budgetPauseModal.seen.${runId}`;
}

export function hasSeenBudgetPauseModal(runId: number): boolean {
  try {
    return sessionStorage.getItem(budgetPauseStorageKey(runId)) === "1";
  } catch {
    return false;
  }
}

export function markBudgetPauseModalSeen(runId: number): void {
  try {
    sessionStorage.setItem(budgetPauseStorageKey(runId), "1");
  } catch {
    /* ignore quota / private mode */
  }
}
