/** Frozen WB-1 foundation stage codes (contract v1). */
export const WHOLE_BOOK_FOUNDATION_STAGES = [
  "snapshot",
  "windowing",
  "extract_entities_events",
  "materialize_assets",
  "synthesize_overview",
  "project_result",
  "finalize",
] as const;

export type WholeBookFoundationStage = (typeof WHOLE_BOOK_FOUNDATION_STAGES)[number];

const STAGE_LABELS: Record<string, string> = {
  snapshot: "快照",
  windowing: "跨章窗口",
  extract_entities_events: "实体与事件抽取",
  materialize_assets: "物化资产",
  synthesize_overview: "合成概览",
  project_result: "投影结果",
  finalize: "收尾",
};

export function foundationStageLabel(stageCode: string | null | undefined): string {
  if (!stageCode) return "—";
  return STAGE_LABELS[stageCode] || stageCode;
}

export type FoundationStageListItem = {
  key: string;
  label: string;
  state: "pending" | "current" | "done";
};

export function buildFoundationStageList(
  stages: Array<{ stage_code: string; status: string }>,
  currentStage: string | null | undefined,
  runStatus?: string | null,
): FoundationStageListItem[] {
  const byCode = new Map(stages.map((s) => [s.stage_code, s.status]));
  const current = currentStage || null;
  const completedRun = runStatus === "completed";

  return WHOLE_BOOK_FOUNDATION_STAGES.map((key) => {
    const stageStatus = byCode.get(key);
    let state: FoundationStageListItem["state"] = "pending";
    if (completedRun || stageStatus === "completed") {
      state = "done";
    } else if (current === key || stageStatus === "running") {
      state = "current";
    }
    return { key, label: foundationStageLabel(key), state };
  });
}
