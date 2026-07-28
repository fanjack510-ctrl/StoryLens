/** Unified Reader Journey status → UI copy (CHG-041 Round 4). */

export type ReaderJourneyUiStatus =
  | "queued"
  | "running"
  | "paused"
  | "interrupted"
  | "failed"
  | "succeeded"
  | "superseded"
  | "unknown";

const RUNNING = new Set([
  "queued",
  "pending",
  "running",
  "scene_profiles_running",
  "chapter_synthesis_running",
  "summary_running",
  "phase_analysis_running",
  "reader_journey_processing",
]);

export function mapReaderJourneyStatusToUi(args: {
  journeyStatus?: string | null;
  resultStatus?: string | null;
  retryable?: boolean | null;
}): {
  status: ReaderJourneyUiStatus;
  label: string;
  sidebarUiState:
    | "reader_journey_processing"
    | "awaiting_reader_journey_start"
    | "partial"
    | "failed"
    | "succeeded"
    | "idle";
} {
  const raw = (args.journeyStatus || "").toLowerCase();
  const result = (args.resultStatus || "").toLowerCase();
  if (result === "superseded") {
    return {
      status: "superseded",
      label: "基于旧场景版本",
      sidebarUiState: "idle",
    };
  }
  if (RUNNING.has(raw) || raw === "queued") {
    if (raw === "queued" || raw === "pending") {
      return {
        status: "queued",
        label: "等待开始",
        sidebarUiState: "reader_journey_processing",
      };
    }
    return {
      status: "running",
      label: "正在生成阅读旅程",
      sidebarUiState: "reader_journey_processing",
    };
  }
  if (raw === "paused") {
    return {
      status: "paused",
      label: "分析已暂停",
      sidebarUiState: "partial",
    };
  }
  if (raw === "interrupted" || raw === "cancelled") {
    return {
      status: "interrupted",
      label: "阅读旅程已中断",
      sidebarUiState: "failed",
    };
  }
  if (raw === "failed" || raw === "budget_blocked" || raw === "aborted_by_limit") {
    return {
      status: "failed",
      label: "阅读旅程生成失败",
      // Never map failed → paused / partial.
      sidebarUiState: "failed",
    };
  }
  if (raw === "succeeded") {
    return {
      status: "succeeded",
      label: "阅读旅程已完成",
      sidebarUiState: "succeeded",
    };
  }
  return {
    status: "unknown",
    label: "阅读旅程状态未知",
    sidebarUiState: "awaiting_reader_journey_start",
  };
}
