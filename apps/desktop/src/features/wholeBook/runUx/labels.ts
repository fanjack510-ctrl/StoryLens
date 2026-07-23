/**
 * User-facing labels for whole-book run UX (Agent J).
 * Stage Key / Module Key are never used as primary titles.
 */

import type {
  RunAllowedAction,
  WholeBookAnalysisMode,
  WholeBookModuleKey,
  WholeBookRunViewStatus,
} from "../contracts/keys";

export const MODULE_DISPLAY_NAMES: Record<WholeBookModuleKey, string> = {
  book_overview: "全书概览",
  structure_stages: "结构阶段",
  chapter_functions: "章节功能",
  storylines: "故事线",
  characters: "人物",
  character_arcs: "人物弧光",
  relationships: "人物关系",
  hooks_payoffs: "伏笔与兑现",
  causal_chain: "因果链",
  basic_timeline: "基础时间线",
  diagnostics: "诊断报告",
};

export const MODE_DISPLAY: Record<
  WholeBookAnalysisMode,
  { title: string; summary: string; bullets: string[] }
> = {
  whole_book_native: {
    title: "Native（原生整书）",
    summary: "使用完整正文 Snapshot，不依赖已有章节分析，适合首次整书分析。",
    bullets: [
      "完整正文 Snapshot 为唯一主来源",
      "不要求已有章节 Scene / Reader Journey",
      "适合首次整书分析",
    ],
  },
  whole_book_enhanced: {
    title: "Enhanced（增强整书）",
    summary: "完整正文仍是主来源；章节 Scene、Reader Journey、章节资产仅作辅助。",
    bullets: [
      "完整正文 Snapshot 仍是第一事实源",
      "章节资产仅作辅助，不足时可降级",
      "显示增强覆盖率",
    ],
  },
};

export const RUN_STATUS_LABELS: Record<WholeBookRunViewStatus, string> = {
  pending: "等待开始",
  running: "运行中",
  paused: "已暂停",
  interrupted: "已中断",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const ACTION_LABELS: Record<RunAllowedAction, string> = {
  pause: "暂停",
  resume: "恢复",
  retry: "重试失败阶段",
  cancel: "取消运行",
  view_partial_results: "查看部分结果",
};

export function formatRatio(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value * 100)}%`;
}
