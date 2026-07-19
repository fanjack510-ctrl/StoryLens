import type { Run } from "../../types";
import { isBudgetPauseRun } from "../../services/budgetPauseDetect";
import { userFacingBudgetMessage } from "../../services/budgetErrorCopy";

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
      return "分析已暂停";
    case "aborted_by_limit":
      return "分析已暂停";
    case "awaiting_budget_adjustment":
      return "分析已暂停";
    case "awaiting_reader_journey_start":
      return "分析已暂停";
    case "reader_journey_processing":
      return "正在生成阅读旅程";
    case "succeeded":
      return "Scene与阅读旅程已完成";
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
    return "Scene Analysis";
  }
  if (stage === "boundary_review" || stage === "boundary_review_generation") {
    return "场景边界";
  }
  if (stage === "reader_journey" || String(stage).startsWith("reader_journey")) {
    return "Reader Journey";
  }
  if (stage === "completed") return "已完成";
  if (run.status === "awaiting_boundary_review") return "等待边界审阅";
  if (run.status === "scene_analysis_running") return "Scene Analysis";
  if (run.status === "boundary_confirmed_budget_blocked") return "Scene Analysis";
  return stage || "进行中";
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
  tone: "done" | "active" | "pending";
};

export function stageSteps(ui: ChapterAnalysisUiState, run?: Run | null): StageStep[] {
  const prepare: StageStep = {
    id: "prepare",
    label: "准备章节",
    tone: ui === "idle" || ui === "creating" ? "active" : "done",
  };

  let analyzeTone: StageStep["tone"] = "pending";
  if (
    ui === "running" ||
    ui === "boundary_review_required" ||
    ui === "provider_recovery" ||
    ui === "partial" ||
    ui === "aborted_by_limit" ||
    ui === "awaiting_budget_adjustment"
  ) {
    analyzeTone = "active";
  } else if (
    ui === "succeeded" ||
    ui === "awaiting_reader_journey_start" ||
    ui === "reader_journey_processing"
  ) {
    analyzeTone = "done";
  } else if (ui === "failed" || ui === "cancelled") {
    analyzeTone = run && (run.completed_scene_count ?? 0) > 0 ? "active" : "pending";
  }

  const analyze: StageStep = {
    id: "analyze",
    label:
      ui === "boundary_review_required"
        ? "等待边界审阅"
        : ui === "provider_recovery"
          ? "等待模型服务恢复"
          : ui === "awaiting_budget_adjustment"
            ? "已暂停 · 等待调整额度"
            : ui === "aborted_by_limit"
              ? "已因限额暂停"
              : "场景识别与分析",
    tone: analyzeTone,
  };

  let journeyTone: StageStep["tone"] = "pending";
  if (ui === "reader_journey_processing") journeyTone = "active";
  else if (ui === "succeeded") journeyTone = "done";
  else if (ui === "awaiting_reader_journey_start") journeyTone = "active";

  const journey: StageStep = {
    id: "reader_journey",
    label:
      ui === "awaiting_reader_journey_start"
        ? "等待生成阅读旅程"
        : ui === "reader_journey_processing"
          ? "正在生成阅读旅程"
          : "阅读旅程",
    tone: journeyTone,
  };

  const results: StageStep = {
    id: "results",
    label: "查看分析结果",
    tone: ui === "succeeded" ? "done" : "pending",
  };

  return [prepare, analyze, journey, results];
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

export function elapsedLabel(run: Run): string | null {
  const start = run.started_at || run.created_at;
  if (!start) return null;
  const end = run.completed_at ? new Date(run.completed_at).getTime() : Date.now();
  const ms = Math.max(0, end - new Date(start).getTime());
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
    return `预估约 ${cost} CNY · 剩余约 ${remaining} CNY`;
  }
  if (typeof cost === "number") return `预估约 ${cost} CNY`;
  if (typeof remaining === "number") return `剩余预算约 ${remaining} CNY`;
  return null;
}
