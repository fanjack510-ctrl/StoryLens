/** User-facing whole-book stage labels (Wave D §8). */
export const WHOLE_BOOK_FREE_USER_STAGES = [
  "snapshot",
  "windowing",
  "extract_entities_events",
  "materialize_assets",
  "synthesize_overview",
  "project_result",
  "finalize",
] as const;

const USER_STAGE_LABELS: Record<string, string> = {
  snapshot: "准备完整原文",
  windowing: "划分分析区段",
  extract_entities_events: "识别人物与关键事件",
  materialize_assets: "整理分析证据",
  synthesize_overview: "生成全书总览",
  /** WB-2.2 — label only; stage list wiring remains Integration-owned. */
  synthesize_chapter_functions: "识别章节功能",
  project_result: "整理结果页面",
  finalize: "完成分析",
};

export function wholeBookFreeStageLabel(stageCode: string | null | undefined): string {
  if (!stageCode) return "—";
  return USER_STAGE_LABELS[stageCode] || stageCode;
}

export type WholeBookFreeStageItem = {
  key: string;
  label: string;
  state: "pending" | "current" | "done" | "failed" | "paused";
};

export function buildWholeBookFreeStageList(
  stages: Array<{ stage_code: string; status: string }>,
  currentStage: string | null | undefined,
  runStatus?: string | null,
): WholeBookFreeStageItem[] {
  const byCode = new Map(stages.map((s) => [s.stage_code, s.status]));
  const current = currentStage || null;
  const completedRun = runStatus === "completed";

  return WHOLE_BOOK_FREE_USER_STAGES.map((key) => {
    const stageStatus = byCode.get(key);
    let state: WholeBookFreeStageItem["state"] = "pending";
    if (completedRun || stageStatus === "completed") {
      state = "done";
    } else if (stageStatus === "failed") {
      state = "failed";
    } else if (stageStatus === "paused" || runStatus === "paused") {
      state = current === key || stageStatus === "running" ? "paused" : state;
      if (current === key || stageStatus === "running") state = "paused";
    } else if (current === key || stageStatus === "running") {
      state = "current";
    }
    return { key, label: wholeBookFreeStageLabel(key), state };
  });
}

export const WHOLE_BOOK_FREE_STATUS_LABELS: Record<string, string> = {
  pending: "等待开始",
  running: "分析中",
  paused: "已暂停",
  recoverable: "可恢复",
  failed: "分析失败",
  completed: "分析完成",
  cancelled: "已取消",
  canceled: "已取消",
};

export function wholeBookFreeStatusLabel(status: string | null | undefined): string {
  if (!status) return "—";
  return WHOLE_BOOK_FREE_STATUS_LABELS[status] || status;
}
