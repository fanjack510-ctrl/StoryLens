/**
 * Shared AnalysisRun lifecycle semantics for book shell, Native Overview,
 * and Task Center (CHG-20260727-014 / CHG-20260727-019).
 *
 * Maps real backend statuses only — does not invent production states.
 */

import type { Run } from "../types";
import {
  resolveCompositeRunLifecycle,
  type CompositeLifecyclePhase,
} from "./compositeRunLifecycle";

export type RunLifecyclePhase =
  | "none"
  | "awaiting_user"
  | "active"
  | "interrupted"
  | "completed"
  | "failed"
  | "cancelled";

export { resolveCompositeRunLifecycle } from "./compositeRunLifecycle";

export type TaskFamily = "chapter" | "native_overview" | "other";

const AWAITING_USER_STATUSES = new Set([
  "awaiting_boundary_review",
]);

const ACTIVE_STATUSES = new Set([
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
  "reader_journey_processing",
  "reader_journey_running",
  "reader_journey_scene_profiles_running",
  "reader_journey_chapter_running",
  "awaiting_provider_recovery",
  "aborted_by_limit",
]);

const COMPLETED_STATUSES = new Set(["completed", "succeeded"]);

const FAILED_STATUSES = new Set([
  "failed",
  "failed_provider",
  "failed_structural",
]);

const CANCELLED_STATUSES = new Set(["cancelled", "review_cancelled", "review_expired"]);

export function isNativeOverviewRun(run: Run | Record<string, unknown>): boolean {
  const taskType = String((run as any).task_type || "");
  const subjectType = String((run as any).subject_type || "");
  const analysisType = String((run as any).analysis_type || "");
  const scopeType = String((run as any).scope_type || "");
  if (taskType === "whole_book_overview") return true;
  if (analysisType === "whole_book_native") return true;
  if (scopeType === "whole_book" && subjectType === "book") return true;
  if (subjectType === "book" && taskType.includes("whole_book")) return true;
  return false;
}

export function isChapterAnalysisRun(run: Run | Record<string, unknown>): boolean {
  if (isNativeOverviewRun(run)) return false;
  const subjectType = String((run as any).subject_type || "chapter");
  return subjectType === "chapter";
}

export function taskFamily(run: Run | Record<string, unknown> | null | undefined): TaskFamily {
  if (!run) return "other";
  if (isNativeOverviewRun(run)) return "native_overview";
  if (isChapterAnalysisRun(run)) return "chapter";
  return "other";
}

/**
 * Normalize a backend status (+ optional run fields) into a lifecycle phase.
 *
 * CHG-20260727-019: when Journey fields exist, composite priority wins over
 * Parent `succeeded` (so active/interrupted Journey never becomes "查看结果").
 * Scene-only Parent succeeded without a Journey row remains completed (017).
 */
export function normalizeRunLifecycle(
  run: Run | Record<string, unknown> | null | undefined,
  _opts?: { treatSucceededAsCompleted?: boolean },
): RunLifecyclePhase {
  if (!run) return "none";
  const status = String((run as any).status || "").toLowerCase();
  if (!status) return "none";

  const journeyStatus = (run as any).journey_status;
  const effective = (run as any).effective_status;
  if (
    journeyStatus ||
    effective === "journey_running" ||
    effective === "journey_failed" ||
    effective === "partial_complete" ||
    effective === "completed"
  ) {
    const composite: CompositeLifecyclePhase = resolveCompositeRunLifecycle({
      parentStatus: status,
      journeyStatus,
      journeyResultAvailable: (run as any).journey_result_available,
      journeyRetryable: (run as any).journey_retryable,
      journeyErrorCode: (run as any).journey_error_code,
      effectiveStatus: effective,
      chapterComplete: (run as any).chapter_complete,
    });
    return composite;
  }

  if (CANCELLED_STATUSES.has(status)) return "cancelled";
  if (FAILED_STATUSES.has(status) || status.startsWith("failed")) return "failed";

  if (AWAITING_USER_STATUSES.has(status)) return "awaiting_user";

  if (COMPLETED_STATUSES.has(status)) {
    return "completed";
  }

  if (ACTIVE_STATUSES.has(status)) return "active";

  return "active";
}

function createdAtMs(run: Run): number {
  const t = Date.parse(run.created_at || "");
  return Number.isFinite(t) ? t : 0;
}

function preferNewer(a: Run, b: Run): Run {
  if (a.id !== b.id) return a.id > b.id ? a : b;
  return createdAtMs(a) >= createdAtMs(b) ? a : b;
}

function pickNewest(runs: Run[]): Run | null {
  if (!runs.length) return null;
  return runs.reduce((best, item) => preferNewer(best, item));
}

/** Chapter re-entry selection: awaiting_user → active → completed → failed/cancelled. */
export function selectChapterReentryRun(
  runs: Run[] | null | undefined,
  chapterId: number | null | undefined,
): Run | null {
  if (!chapterId || !runs?.length) return null;
  const chapterRuns = runs.filter(
    (run) =>
      isChapterAnalysisRun(run) && String(run.subject_id) === String(chapterId),
  );
  if (!chapterRuns.length) return null;

  const awaiting = chapterRuns.filter((r) => normalizeRunLifecycle(r) === "awaiting_user");
  if (awaiting.length) return pickNewest(awaiting);

  const active = chapterRuns.filter((r) => normalizeRunLifecycle(r) === "active");
  if (active.length) {
    // Prefer in-flight pipeline statuses over succeeded-but-incomplete (journey pending).
    const hardActive = active.filter((r) => String(r.status) !== "succeeded");
    return pickNewest(hardActive.length ? hardActive : active);
  }

  const interrupted = chapterRuns.filter((r) => normalizeRunLifecycle(r) === "interrupted");
  if (interrupted.length) return pickNewest(interrupted);

  const chapterDone = chapterRuns.filter(
    (r) => r.status === "succeeded" && r.chapter_complete === true,
  );
  if (chapterDone.length) return pickNewest(chapterDone);

  const succeeded = chapterRuns.filter(
    (r) => normalizeRunLifecycle(r, { treatSucceededAsCompleted: true }) === "completed",
  );
  if (succeeded.length) return pickNewest(succeeded);

  const terminal = chapterRuns.filter((r) => {
    const p = normalizeRunLifecycle(r);
    return p === "failed" || p === "cancelled";
  });
  return pickNewest(terminal);
}

/** Native Overview re-entry for a book: active → completed → failed/cancelled. */
export function selectNativeOverviewReentryRun(
  runs: Run[] | null | undefined,
  bookId: number | null | undefined,
): Run | null {
  if (!bookId || !runs?.length) return null;
  const bookRuns = runs.filter((run) => {
    if (!isNativeOverviewRun(run)) return false;
    const bid = Number((run as any).book_id ?? run.subject_id);
    return Number.isFinite(bid) && bid === Number(bookId);
  });
  if (!bookRuns.length) return null;

  const active = bookRuns.filter((r) => normalizeRunLifecycle(r) === "active");
  if (active.length) return pickNewest(active);

  const completed = bookRuns.filter((r) => normalizeRunLifecycle(r) === "completed");
  if (completed.length) return pickNewest(completed);

  const terminal = bookRuns.filter((r) => {
    const p = normalizeRunLifecycle(r);
    return p === "failed" || p === "cancelled";
  });
  return pickNewest(terminal);
}

export function nativeOverviewHref(bookId: number, runId: number): string {
  return `/books/${bookId}/pro-native-overview?run_id=${runId}`;
}

export function chapterConfirmHref(args: {
  bookId: number;
  chapterId: number | string;
  analysisRunId: number;
}): string {
  const params = new URLSearchParams();
  params.set("chapter", String(args.chapterId));
  params.set("analysisRun", String(args.analysisRunId));
  params.set("view", "progress");
  return `/books/${args.bookId}?${params.toString()}`;
}

export type TaskCenterPrimaryAction = {
  kind: "progress" | "confirm" | "result" | "detail" | "retry" | "none";
  label: string;
  testId: string;
};

export function resolveTaskCenterPrimaryAction(run: Run | Record<string, unknown>): TaskCenterPrimaryAction {
  const status = String((run as any).status || "").toLowerCase();
  const id = Number((run as any).id || 0);

  // Recoverable partial scene analysis opens the detail/recovery panel (not progress nav).
  if (status === "scene_analysis_partial" || status === "boundary_candidates_partial") {
    return { kind: "detail", label: "查看详情", testId: `view-detail-${id}` };
  }

  const phase = normalizeRunLifecycle(run as Run);
  const journeyResultAvailable = Boolean((run as any).journey_result_available);
  const chapterComplete = (run as any).chapter_complete === true;

  if (phase === "awaiting_user") {
    return { kind: "confirm", label: "继续确认", testId: `continue-confirm-${id}` };
  }
  if (phase === "active") {
    return { kind: "progress", label: "查看进度", testId: `view-progress-${id}` };
  }
  if (phase === "interrupted") {
    return { kind: "detail", label: "查看详情", testId: `view-detail-${id}` };
  }
  if (phase === "completed") {
    // Journey final artifact required when a journey row participated.
    if ((run as any).journey_status && !journeyResultAvailable && !chapterComplete) {
      return { kind: "detail", label: "查看详情", testId: `view-detail-${id}` };
    }
    const label =
      journeyResultAvailable || chapterComplete ? "查看分析结果" : "查看结果";
    return { kind: "result", label, testId: `view-results-${id}` };
  }
  if (phase === "failed") {
    return { kind: "detail", label: "查看详情", testId: `view-detail-${id}` };
  }
  if (phase === "cancelled") {
    return { kind: "detail", label: "查看详情", testId: `view-detail-${id}` };
  }
  return { kind: "none", label: "", testId: "" };
}

/** Extract ANALYSIS_RUN_EXISTS details from ApiError.detail without inventing IDs. */
export function existingRunDetailsFromError(error: {
  code?: string;
  detail?: unknown;
}): {
  existing_run_id: number;
  existing_run_status?: string;
  existing_run_type?: string;
  book_id?: number;
  chapter_id?: number;
} | null {
  if (error.code !== "ANALYSIS_RUN_EXISTS") return null;
  const detail = error.detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const d = detail as Record<string, unknown>;
  // details may be nested under .details from older shapes
  const bag =
    d.existing_run_id != null
      ? d
      : d.details && typeof d.details === "object" && !Array.isArray(d.details)
        ? (d.details as Record<string, unknown>)
        : null;
  if (!bag || bag.existing_run_id == null) return null;
  const id = Number(bag.existing_run_id);
  if (!Number.isFinite(id) || id <= 0) return null;
  return {
    existing_run_id: id,
    existing_run_status:
      bag.existing_run_status != null ? String(bag.existing_run_status) : undefined,
    existing_run_type:
      bag.existing_run_type != null ? String(bag.existing_run_type) : undefined,
    book_id: bag.book_id != null ? Number(bag.book_id) : undefined,
    chapter_id: bag.chapter_id != null ? Number(bag.chapter_id) : undefined,
  };
}
