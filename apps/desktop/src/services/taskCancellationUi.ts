/**
 * Task Center cooperative stop (CHG-20260729-006).
 * Presentation only — cancel authority is the API + persisted run state.
 */

export const STOP_CONFIRM_TITLE = "确定停止本次分析吗？";

export const STOP_CONFIRM_BODY = [
  "停止后将不再处理剩余场景，也不会再发起新的模型请求。",
  "已完成的分析结果和已产生的用量会保留。",
  "已经发出的模型请求可能仍会完成并产生相应用量。",
  "需要再次分析时，将创建一个新任务。",
].join("\n");

const STOPPABLE = new Set([
  "queued",
  "pending",
  "preparing",
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
  "awaiting_boundary_review",
  "aborted_by_limit",
  "retrying",
]);

const STOPPING = new Set(["cancellation_requested", "stopping"]);

const TERMINAL_NO_STOP = new Set([
  "succeeded",
  "completed",
  "failed",
  "failed_provider",
  "failed_structural",
  "cancelled",
  "review_cancelled",
  "review_expired",
  "superseded",
]);

export function isStoppingStatus(status: string | undefined | null): boolean {
  return STOPPING.has(String(status || "").toLowerCase());
}

export function isCancelledStatus(status: string | undefined | null): boolean {
  const s = String(status || "").toLowerCase();
  return s === "cancelled" || s === "review_cancelled";
}

export function canShowStopAnalysis(run: {
  status?: string;
  can_cancel?: boolean;
} | null | undefined): boolean {
  if (!run) return false;
  if (run.can_cancel === false) return false;
  const status = String(run.status || "").toLowerCase();
  if (!status) return false;
  if (STOPPING.has(status) || TERMINAL_NO_STOP.has(status)) return false;
  if (run.can_cancel === true) return true;
  return STOPPABLE.has(status);
}

export function taskCancelStatusLabel(status: string | undefined | null): string | null {
  const s = String(status || "").toLowerCase();
  if (STOPPING.has(s)) return "正在停止";
  if (s === "cancelled" || s === "review_cancelled") return "已停止";
  return null;
}

export function cancellationReasonLabel(reason: string | undefined | null): string {
  if (reason === "user_requested") return "用户主动停止";
  return reason ? String(reason) : "—";
}

export function formatCancelDetailHint(run: {
  status?: string;
  completed_scene_count?: number | null;
  total_scene_count?: number | null;
  remaining_scene_count?: number | null;
}): string | null {
  if (!isCancelledStatus(run.status) && !isStoppingStatus(run.status)) return null;
  const done = Number(run.completed_scene_count ?? 0);
  const total = Number(run.total_scene_count ?? 0);
  const remaining =
    run.remaining_scene_count != null
      ? Number(run.remaining_scene_count)
      : total > 0
        ? Math.max(0, total - done)
        : null;
  if (total > 0) {
    return `已完成场景：${done} / ${total}${
      remaining != null ? `；剩余场景：${remaining}` : ""
    }。已完成结果已保留，但本次分析未形成完整章节结果。`;
  }
  return "已完成结果已保留，但本次分析未形成完整章节结果。";
}
