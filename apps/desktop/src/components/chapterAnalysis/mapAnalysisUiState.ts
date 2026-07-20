import type { Run } from "../../types";
import { isBudgetPauseRun } from "../../services/budgetPauseDetect";
import { userFacingBudgetMessage } from "../../services/budgetErrorCopy";
import { formatCny } from "../analysis/analysisDisplayLabels";

/** Frontend-only composition states; never persisted as a second backend enum. */
export type ChapterAnalysisUiState =
  | "idle"
  | "preflight_loading"
  | "awaiting_consent"
  | "creating"
  | "running"
  | "boundary_review_required"
  | "provider_recovery"
  | "partial"
  | "failed"
  | "aborted_by_limit"
  | "awaiting_budget_adjustment"
  | "awaiting_reader_journey_start"
  | "reader_journey_processing"
  | "succeeded"
  | "cancelled";

/** Full chapter success only. Journey-incomplete states keep polling journey APIs. */
const TERMINAL: ChapterAnalysisUiState[] = ["succeeded", "failed", "cancelled"];

const STAGE_STEP_DEFS = [
  { id: "prepare", label: "准备章节" },
  { id: "boundary_identify", label: "识别场景边界" },
  { id: "boundary_review", label: "确认场景边界" },
  { id: "analyze", label: "分析场景" },
  { id: "journey", label: "生成读者旅程" },
  { id: "complete", label: "完成" },
] as const;

export function isTerminalUiState(state: ChapterAnalysisUiState): boolean {
  return TERMINAL.includes(state);
}

export function mapRunToUiState(run: Run | null | undefined): ChapterAnalysisUiState {
  if (!run) return "idle";
  const status = run.status || "";

  if (status === "succeeded") return "succeeded";
  if (status === "cancelled" || status === "review_cancelled") return "cancelled";
  if (status === "awaiting_boundary_review") return "boundary_review_required";
  if (status === "awaiting_provider_recovery") return "provider_recovery";
  if (isBudgetPauseRun(run)) return "awaiting_budget_adjustment";
  if (status === "aborted_by_limit") return "aborted_by_limit";
  if (
    status === "scene_analysis_partial" ||
    status === "boundary_candidates_partial"
  ) {
    return "partial";
  }
  if (
    status === "failed" ||
    status === "failed_provider" ||
    status === "failed_structural" ||
    status === "review_expired" ||
    status.startsWith("failed")
  ) {
    return "failed";
  }
  // queued / running / boundary_* / scene_analysis_running / boundary_confirmed
  return "running";
}

export function uiStateLabel(state: ChapterAnalysisUiState): string {
  switch (state) {
    case "idle":
      return "开始分析";
    case "preflight_loading":
      return "正在估算分析费用";
    case "awaiting_consent":
      return "请确认分析设置";
    case "creating":
      return "正在启动分析";
    case "running":
      return "正在分析本章";
    case "boundary_review_required":
      return "需要确认场景边界";
    case "provider_recovery":
      return "分析已暂停";
    case "partial":
      return "分析已暂停";
    case "failed":
      return "分析未完成";
    case "aborted_by_limit":
      return "分析已暂停";
    case "awaiting_budget_adjustment":
      return "分析已暂停";
    case "awaiting_reader_journey_start":
      return "分析已暂停";
    case "reader_journey_processing":
      return "正在生成阅读旅程";
    case "succeeded":
      return "分析完成";
    case "cancelled":
      return "任务已取消";
    default:
      return "分析状态";
  }
}

export function stageLabelForRun(run: Run | null | undefined): string {
  if (!run) return "—";
  const stage = run.current_stage || run.failed_stage || "";
  if (stage === "scene_analysis" || stage === "scene_analysis_budget") {
    return "正在分析场景";
  }
  if (stage === "boundary_review" || stage === "boundary_review_generation") {
    return "确认场景边界";
  }
  if (stage === "boundary_generation") {
    return "识别场景边界";
  }
  if (stage === "reader_journey" || String(stage).startsWith("reader_journey")) {
    return "正在生成阅读旅程";
  }
  if (stage === "completed") return "完成";
  if (run.status === "awaiting_boundary_review") return "确认场景边界";
  if (run.status === "scene_analysis_running") return "正在分析场景";
  if (run.status === "boundary_confirmed_budget_blocked") return "正在分析场景";
  return stage || "进行中";
}

export function currentWorkLabel(
  ui: ChapterAnalysisUiState,
  run?: Run | null,
): string | null {
  switch (ui) {
    case "idle":
    case "preflight_loading":
    case "awaiting_consent":
    case "creating":
      return uiStateLabel(ui);
    case "running":
    case "boundary_review_required":
    case "reader_journey_processing":
    case "awaiting_reader_journey_start":
      return stageLabelForRun(run);
    case "provider_recovery":
    case "partial":
    case "aborted_by_limit":
    case "awaiting_budget_adjustment":
      return "分析已暂停";
    case "failed":
      return "分析未完成";
    case "succeeded":
      return "分析完成";
    case "cancelled":
      return "任务已取消";
    default:
      return null;
  }
}

export function readerJourneyStageLabel(
  run: Run | null | undefined,
  composition?: ChapterAnalysisUiState,
): string {
  if (composition === "succeeded") return "已完成";
  if (composition === "reader_journey_processing") return "进行中";
  if (composition === "awaiting_reader_journey_start") return "尚未生成";
  if (!run) return "未开始";
  if (run.status === "succeeded") return "可生成";
  const stage = run.current_stage || "";
  if (String(stage).startsWith("reader_journey")) return "进行中";
  return "未开始";
}

export function progressCounts(run: Run | null | undefined): {
  current: number;
  total: number;
} {
  if (!run) return { current: 0, total: 0 };
  if (typeof run.total_scene_count === "number" && run.total_scene_count > 0) {
    return {
      current: run.completed_scene_count ?? 0,
      total: run.total_scene_count,
    };
  }
  return {
    current: run.progress_current ?? 0,
    total: run.progress_total ?? 0,
  };
}

/** Stage checklist — only labels backed by observable run fields. */
export type StageStep = {
  id: string;
  label: string;
  tone: "done" | "active" | "pending" | "failed";
};

function stageToPhase(stage: string): number {
  if (!stage) return -1;
  if (stage === "preparing") return 0;
  if (stage === "boundary_generation" || stage === "boundary_review_generation") return 1;
  if (stage === "boundary_review") return 2;
  if (stage.startsWith("scene_analysis")) return 3;
  if (stage.startsWith("reader_journey")) return 4;
  if (stage === "completed") return 5;
  if (stage.startsWith("boundary")) return 1;
  return -1;
}

function activePhaseForUi(ui: ChapterAnalysisUiState, run?: Run | null): number {
  if (ui === "idle" || ui === "preflight_loading" || ui === "awaiting_consent" || ui === "creating") {
    return 0;
  }
  if (ui === "boundary_review_required") return 2;
  if (ui === "reader_journey_processing" || ui === "awaiting_reader_journey_start") return 4;
  if (ui === "succeeded") return 5;

  const stage = run?.current_stage || run?.failed_stage || "";
  const mapped = stageToPhase(stage);
  if (mapped >= 0) return mapped;

  if (
    ui === "running" ||
    ui === "partial" ||
    ui === "provider_recovery" ||
    ui === "awaiting_budget_adjustment" ||
    ui === "aborted_by_limit" ||
    ui === "failed"
  ) {
    return 3;
  }
  return 0;
}

function failedPhaseForUi(ui: ChapterAnalysisUiState, run?: Run | null): number | null {
  if (ui !== "failed" && ui !== "cancelled") return null;
  const stage = run?.failed_stage || run?.current_stage || "";
  const mapped = stageToPhase(stage);
  return mapped >= 0 ? mapped : null;
}

export function stageSteps(ui: ChapterAnalysisUiState, run?: Run | null): StageStep[] {
  const activePhase = activePhaseForUi(ui, run);
  const failedPhase = failedPhaseForUi(ui, run);

  return STAGE_STEP_DEFS.map((step, index) => {
    let tone: StageStep["tone"] = "pending";
    if (failedPhase != null) {
      if (index < failedPhase) tone = "done";
      else if (index === failedPhase) tone = "failed";
      else tone = "pending";
    } else if (ui === "succeeded") {
      tone = "done";
    } else if (index < activePhase) {
      tone = "done";
    } else if (index === activePhase) {
      tone = "active";
    }

    return { id: step.id, label: step.label, tone };
  });
}

export function userFacingFailureHint(run: Run): string {
  if (isBudgetPauseRun(run)) {
    return (
      userFacingBudgetMessage(run.error_code || run.root_error_code) ||
      "已因预算或请求限额暂停，请调整限额后恢复；已完成结果不会丢失。"
    );
  }
  if (run.user_action_hint?.trim()) return run.user_action_hint.trim();
  if (run.failed_stage === "scene_analysis") {
    return "场景分析未全部完成，可尝试恢复剩余任务。";
  }
  if (run.failed_stage === "provider_request" || run.status === "failed_provider") {
    return "模型请求未完成，可尝试从已保存进度恢复。";
  }
  if (run.status === "boundary_candidates_partial") {
    return "场景边界识别部分完成，可继续恢复。";
  }
  if (run.status === "scene_analysis_partial") {
    return "部分场景已分析完成，可继续恢复剩余场景。";
  }
  if (run.status === "awaiting_provider_recovery") {
    return "模型服务暂时不可用，已保存成功场景结果；恢复后将继续未完成场景。";
  }
  if (
    run.status === "boundary_confirmed_budget_blocked" ||
    run.status === "aborted_by_limit"
  ) {
    return "已因预算或请求限额暂停，请调整限额后恢复；已完成结果不会丢失。";
  }
  if (
    run.root_error_code === "CLOUD_BUDGET_EXCEEDED" ||
    run.root_error_code === "CLOUD_REQUEST_LIMIT_EXCEEDED" ||
    run.root_error_code === "CLOUD_TOKEN_LIMIT_EXCEEDED" ||
    run.root_error_code === "CLOUD_COST_LIMIT_EXCEEDED" ||
    run.failed_stage === "budget_gate"
  ) {
    return "今日云端分析额度不足，请调整预算后继续同一任务。";
  }
  return "分析未完成，可查看技术详情或尝试恢复。";
}

const MAX_ELAPSED_MS = 48 * 60 * 60 * 1000;

export function elapsedLabel(run: Run): string | null {
  const start = run.started_at || run.created_at;
  if (!start) return null;
  const startMs = new Date(start).getTime();
  if (!Number.isFinite(startMs)) return null;

  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  if (!Number.isFinite(end)) return null;
  if (end < startMs) return null;

  const ms = end - startMs;
  if (ms > MAX_ELAPSED_MS) return null;

  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return `${min} 分 ${rem} 秒`;
  const hr = Math.floor(min / 60);
  return `${hr} 小时 ${min % 60} 分`;
}

export function budgetSummary(run: Run): string | null {
  const cost = run.budget_required?.estimated_cost;
  const remaining = run.budget_remaining?.estimated_cost;
  if (typeof cost === "number" && typeof remaining === "number") {
    return `${formatCny(cost, "预估费用未知")} · 剩余${formatCny(remaining, "剩余预算未知")}`;
  }
  if (typeof cost === "number") return formatCny(cost, "预估费用未知");
  if (typeof remaining === "number") return `剩余${formatCny(remaining, "剩余预算未知")}`;
  return null;
}
