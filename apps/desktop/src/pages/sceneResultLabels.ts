/** User-facing labels for Scene Analysis result panels. Raw field keys stay in tech details. */

import type { SceneAnalysisFields } from "../types";

export const STRUCTURE_FIELD_SECTIONS: {
  key: keyof SceneAnalysisFields;
  label: string;
  section: string;
}[] = [
  { key: "entry_state", label: "进入状态", section: "人物" },
  { key: "goal", label: "目标", section: "目标" },
  { key: "obstacle", label: "冲突与阻碍", section: "冲突" },
  { key: "turning_point", label: "转折", section: "转折" },
  { key: "outcome", label: "结果", section: "结果" },
  { key: "unresolved_question", label: "悬而未决", section: "悬念" },
];

export const EVIDENCE_GROUP_LABELS: { group: string; label: string }[] = [
  { group: "entry_state", label: "人物状态证据" },
  { group: "goal", label: "目标证据" },
  { group: "obstacle", label: "冲突证据" },
  { group: "key_actions", label: "关键动作证据" },
  { group: "turning_point", label: "转折证据" },
  { group: "outcome", label: "结果证据" },
  { group: "unresolved_question", label: "悬念证据" },
];

const BOUNDARY_SOURCE_LABELS: Record<string, string> = {
  chapter_end: "章末",
  model: "模型建议",
  model_accepted: "已接受模型建议",
  user_added: "人工新增",
  user_accepted_model: "已接受模型建议",
  user_accepted_model_conflict: "人工接受冲突边界",
};

const FUNCTION_TAG_LABELS: Record<string, string> = {
  setup: "铺垫",
  payoff: "兑现",
  conflict: "冲突",
  reveal: "揭示",
  transition: "过渡",
  climax: "高潮",
  hook: "钩子",
  character: "人物",
  worldbuilding: "世界观",
  事件推进: "事件推进",
  人物塑造: "人物塑造",
};

export function formatBoundarySource(raw: unknown): string {
  if (raw == null) return "章末";
  const key = String(raw).trim();
  if (!key) return "章末";
  return BOUNDARY_SOURCE_LABELS[key] || key;
}

export function formatFunctionTag(raw: unknown): string {
  if (raw == null) return "";
  const key = String(raw).trim();
  if (!key) return "";
  return FUNCTION_TAG_LABELS[key] || FUNCTION_TAG_LABELS[key.toLowerCase()] || key;
}

export function formatFunctionTags(tags: unknown): string {
  if (!Array.isArray(tags) || tags.length === 0) return "无";
  return tags.map(formatFunctionTag).filter(Boolean).join(" · ") || "无";
}

export function formatSceneSummary(analysis: SceneAnalysisFields | undefined | null): string {
  if (!analysis) return "暂无场景摘要";
  const parts = [analysis.entry_state?.summary, analysis.goal?.summary, analysis.outcome?.summary]
    .map((part) => (typeof part === "string" ? part.trim() : ""))
    .filter(Boolean);
  if (!parts.length) return "暂无场景摘要";
  return parts.slice(0, 2).join("；");
}

export function formatRunStatusForResults(status: unknown): string {
  const key = status == null ? "" : String(status).trim();
  if (!key) return "未知状态";
  const map: Record<string, string> = {
    queued: "排队中",
    running: "进行中",
    failed: "失败",
    succeeded: "已完成",
    cancelled: "已取消",
    aborted_by_limit: "已暂停",
    scene_analysis_partial: "部分完成",
    boundary_candidates_partial: "部分完成",
    awaiting_boundary_review: "等待边界确认",
    awaiting_provider_recovery: "已暂停",
    boundary_confirmed_budget_blocked: "已暂停",
  };
  return map[key] || "处理中";
}
