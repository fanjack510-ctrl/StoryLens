/**
 * Overview production stages (contract OverviewProductionStageKey).
 * UI lists these for multi-stage progress — no invented percentages.
 */

export const OVERVIEW_PRODUCTION_STAGES = [
  "snapshot_preflight",
  "build_context_windows",
  "extract_overview_facts",
  "materialize_assets",
  "generate_overview_projection",
  "finalize",
] as const;

export type OverviewProductionStage = (typeof OVERVIEW_PRODUCTION_STAGES)[number];

const STAGE_LABELS: Record<string, string> = {
  snapshot_preflight: "快照预检",
  build_context_windows: "构建上下文窗口",
  extract_overview_facts: "抽取概览事实",
  materialize_assets: "物化资产",
  generate_overview_projection: "生成概览投影",
  finalize: "收尾确认",
};

export function overviewStageLabel(stageKey: string | null | undefined): string {
  if (!stageKey) return "—";
  return STAGE_LABELS[stageKey] || stageKey;
}

export type StageListItem = {
  key: string;
  label: string;
  state: "pending" | "current" | "done";
};

/** Build ordered stage list with current stage highlighted (no fake %). */
export function buildStageList(
  currentStage: string | null | undefined,
  runStatus?: string | null,
): StageListItem[] {
  const current = currentStage || null;
  const currentIndex = current
    ? OVERVIEW_PRODUCTION_STAGES.indexOf(current as OverviewProductionStage)
    : -1;
  const completedRun = runStatus === "completed";

  return OVERVIEW_PRODUCTION_STAGES.map((key, index) => {
    let state: StageListItem["state"] = "pending";
    if (completedRun) {
      state = "done";
    } else if (currentIndex >= 0) {
      if (index < currentIndex) state = "done";
      else if (index === currentIndex) state = "current";
    } else if (current === key) {
      state = "current";
    }
    return { key, label: overviewStageLabel(key), state };
  });
}

export const FIELD_STATUS_LABELS: Record<string, string> = {
  supported: "已支持",
  low_confidence: "低置信度",
  insufficient_evidence: "证据不足",
  conflicted: "存在冲突",
};

export function fieldStatusLabel(status: string | null | undefined): string {
  if (!status) return "缺失";
  return FIELD_STATUS_LABELS[status] || status;
}
