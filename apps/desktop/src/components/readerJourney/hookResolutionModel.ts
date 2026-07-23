/**
 * Hook resolution (钩子回收) presentation model.
 * Reads NarrativeLoopView facts only — does not change analysis formulas.
 *
 * Main status is singular per loop; conflict is an additive flag.
 * Stats invariant: resolved + partial + unresolved === established.
 */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  getNarrativeLoops,
  type NarrativeLoopConflict,
  type NarrativeLoopPayoff,
  type NarrativeLoopView,
  type RelationGrade,
} from "./narrativeLoopView";
import { shortPlainTitle } from "./readerJourneyLensExplanation";

export type HookMainStatus = "resolved" | "partial" | "unresolved";

export type HookResolutionLineStyle = "solid" | "dashed" | "gray";

export type HookConflictItem = {
  loop_id: string;
  short_title: string;
  main_status: HookMainStatus;
  main_label: string;
  conflict_point: string;
  reason: string;
};

export type HookResolutionRow = {
  loop_id: string;
  short_title: string;
  full_title: string;
  open_scene: number;
  resolve_scene: number | null;
  main_status: HookMainStatus;
  main_label: string;
  has_conflict: boolean;
  conflict_label: string | null;
  payoff_type_label: string | null;
  line_style: HookResolutionLineStyle;
  evidence_paragraph_ids: string[];
  locate_scene: number;
};

export type HookResolutionChapterStats = {
  established: number;
  resolved: number;
  partial: number;
  unresolved: number;
  conflict: number;
};

export type HookResolutionModel = {
  stats: HookResolutionChapterStats;
  verdict: string;
  conflicts: HookConflictItem[];
  rows: HookResolutionRow[];
  max_scene: number;
  empty: boolean;
};

export const HOOK_RESOLUTION_TAB_LABEL = "钩子回收";
export const HOOK_RESOLUTION_CONCLUSION_TITLE = "本章钩子回收结论";
export const HOOK_RESOLUTION_CONFLICT_TITLE = "冲突提醒";
export const HOOK_RESOLUTION_OVERVIEW_TITLE = "钩子回收总览";
export const HOOK_RESOLUTION_LIST_TITLE = "钩子清单";

export const MAIN_STATUS_LABEL: Record<HookMainStatus, string> = {
  resolved: "已回收",
  partial: "部分回收",
  unresolved: "未回收",
};

const CONFLICT_REASON_ZH: Record<string, string> = {
  payoff_score_without_entity: "分数路径与实体证据不一致",
  payoff_entity_without_evidence: "结构回收缺少文本证据",
  hook_without_question: "钩子缺少明确问题表述",
  risk_loop_divergence: "阻力区间与钩子链不一致",
  fingerprint_mismatch: "文本指纹不一致",
  run_mismatch: "分析批次不一致",
  scope_mismatch: "作用范围不一致",
  no_text_evidence: "缺少文本证据",
  multiple_candidates: "存在多个弱候选回收",
  soft_conflict: "承接对象不稳定",
};

function displayStatus(loop: NarrativeLoopView): string {
  return String(loop.display_status || loop.status || "open").toLowerCase();
}

function isHardBlocked(loop: NarrativeLoopView): boolean {
  return Boolean(
    loop.hard_blocked ||
      loop.consistency_status === "inconsistent" ||
      displayStatus(loop) === "inconsistent",
  );
}

function hasSoftConflict(loop: NarrativeLoopView): boolean {
  return Boolean(
    loop.soft_conflict ||
      loop.consistency_status === "soft_conflict" ||
      (loop.conflicts || []).length > 0,
  );
}

function openSceneOf(loop: NarrativeLoopView): number {
  return (
    loop.open_from_scene ??
    loop.hook?.[0]?.scene_ordinal ??
    loop.developments?.[0]?.scene_ordinal ??
    1
  );
}

function entityPayoffs(loop: NarrativeLoopView): NarrativeLoopPayoff[] {
  return (loop.payoffs || []).filter(
    (p) =>
      p &&
      p.source_type !== "score_inferred" &&
      String(p.type || "") !== "score_inferred",
  );
}

function primaryPayoff(loop: NarrativeLoopView): NarrativeLoopPayoff | null {
  const pref = loop.primary_relation?.payoff_ref;
  const grade = loop.primary_relation?.grade as RelationGrade | undefined;
  if (
    pref?.scene_ordinal &&
    grade &&
    grade !== "unsupported" &&
    !loop.primary_relation?.blocked
  ) {
    const matched = entityPayoffs(loop).find((p) => p.scene_ordinal === pref.scene_ordinal);
    if (matched) return matched;
    if (pref.source_type === "score_inferred" || pref.type === "score_inferred") {
      return null;
    }
    return {
      scene_ordinal: pref.scene_ordinal,
      type: String(pref.type || "partial"),
      source_type: pref.source_type,
      summary: pref.summary || "",
      evidence_paragraph_ids: pref.evidence_paragraph_ids || [],
    };
  }
  const entities = entityPayoffs(loop);
  if (!entities.length) return null;
  const rank = (type: string) => {
    if (type === "full") return 4;
    if (type === "reversal") return 3;
    if (type === "transformed_question") return 2;
    if (type === "partial") return 1;
    return 0;
  };
  return [...entities].sort(
    (a, b) => rank(String(b.type || "")) - rank(String(a.type || "")),
  )[0];
}

function payoffTypeLabel(type: string | null | undefined): string | null {
  const t = String(type || "");
  if (t === "full") return "直接回收";
  if (t === "partial") return "部分回收";
  if (t === "reversal") return "反转回收";
  if (t === "transformed_question") return "转化回收";
  return null;
}

function conflictPoint(loop: NarrativeLoopView): string {
  const codes = (loop.conflicts || []).map((c) => c.code);
  if (codes.some((c) => String(c).includes("candidate") || String(c).includes("multiple"))) {
    return "存在多个弱候选";
  }
  if (codes.some((c) => String(c).includes("score"))) {
    return "实体与分数路径不一致";
  }
  if (codes.some((c) => String(c).includes("evidence"))) {
    return "结构与文本证据不一致";
  }
  if (isHardBlocked(loop)) return "硬冲突阻断可靠承接";
  if (loop.soft_conflict) return "承接对象不稳定";
  if ((loop.candidate_relations || []).length > 1) return "存在多个弱候选";
  return "判定路径存在分歧";
}

function conflictReasonText(loop: NarrativeLoopView): string {
  const first = (loop.conflicts || [])[0] as NarrativeLoopConflict | undefined;
  if (first?.message && String(first.message).trim()) {
    return String(first.message).trim().slice(0, 48);
  }
  if (first?.code && CONFLICT_REASON_ZH[first.code]) {
    return CONFLICT_REASON_ZH[first.code];
  }
  if (loop.relation_warning) return String(loop.relation_warning).slice(0, 48);
  if (isHardBlocked(loop)) return "严重冲突，结果仅供参考";
  return CONFLICT_REASON_ZH.soft_conflict;
}

/**
 * Singular main status for one NarrativeLoop in chapter scope.
 * Conflict never replaces the main status.
 */
export function resolveHookMainStatus(loop: NarrativeLoopView): {
  main_status: HookMainStatus;
  has_conflict: boolean;
  resolve_scene: number | null;
  payoff_type_label: string | null;
  evidence_paragraph_ids: string[];
} {
  const status = displayStatus(loop);
  const payoff = primaryPayoff(loop);
  const grade = (loop.primary_relation?.grade || null) as RelationGrade | null;
  const conflict = isHardBlocked(loop) || hasSoftConflict(loop);
  const evidence = [
    ...(payoff?.evidence_paragraph_ids || []),
    ...(loop.evidence || []),
  ].filter(Boolean);

  // Weak score-only candidates never count as resolution.
  const weakOnly =
    !payoff &&
    Boolean(loop.primary_relation?.payoff_ref) &&
    (loop.primary_relation?.payoff_ref?.source_type === "score_inferred" ||
      loop.primary_relation?.payoff_ref?.type === "score_inferred");

  let main: HookMainStatus = "unresolved";

  if (status === "resolved" || status === "abandoned") {
    main = "resolved";
  } else if (status === "transformed") {
    main = "partial";
  } else if (status === "partially_resolved") {
    main = "partial";
  } else if (status === "open") {
    main = "unresolved";
  } else if (status === "inconsistent" || isHardBlocked(loop)) {
    // Still pick a main conclusion under hard conflict.
    if (payoff) {
      const t = String(payoff.type || "");
      if (t === "full" && (grade === "confirmed" || grade === "probable")) {
        main = "resolved";
      } else if (t === "full" || t === "partial" || t === "reversal" || t === "transformed_question") {
        main = t === "full" ? "resolved" : "partial";
      } else {
        main = "partial";
      }
    } else {
      main = "unresolved";
    }
  } else if (payoff) {
    const t = String(payoff.type || "");
    if (t === "full" && grade === "confirmed") main = "resolved";
    else if (t === "full" || t === "partial" || t === "reversal" || t === "transformed_question") {
      main = t === "full" && grade !== "candidate" ? "resolved" : "partial";
    } else main = "partial";
  }

  if (weakOnly && main === "resolved") {
    main = "unresolved";
  }
  if (weakOnly && main === "partial" && grade === "candidate") {
    main = "unresolved";
  }

  return {
    main_status: main,
    has_conflict: conflict,
    resolve_scene: main === "unresolved" ? null : payoff?.scene_ordinal ?? null,
    payoff_type_label: payoffTypeLabel(payoff?.type),
    evidence_paragraph_ids: evidence.map(String),
  };
}

export function buildChapterVerdict(stats: HookResolutionChapterStats): string {
  if (stats.established === 0) {
    return "本章未识别出明确钩子。";
  }
  const { resolved, partial, unresolved, established, conflict } = stats;
  let core: string;
  if (resolved === established) {
    core = "本章钩子均已回收。";
  } else if (resolved > partial && resolved > unresolved) {
    core = "本章钩子以已回收为主。";
  } else if (partial > resolved && partial >= unresolved) {
    core = "本章钩子以部分回收为主，暂无全部完全闭合。";
  } else if (unresolved > resolved && unresolved >= partial) {
    core =
      resolved + partial > 0
        ? "本章大多数钩子尚未完全回收，但已出现若干承接与局部回应。"
        : "本章钩子大多尚未回收，仍在等待后续回应。";
  } else if (resolved === 0 && partial > 0) {
    core = "本章钩子以部分回收为主，暂无完全闭合的回收。";
  } else {
    core = "本章钩子回收情况不一，需结合清单逐条查看。";
  }
  if (conflict > 0) {
    return `${core}另有 ${conflict} 个钩子存在判定冲突。`;
  }
  return core;
}

export function buildHookResolutionModel(
  visualization: ReaderJourneyVisualization,
): HookResolutionModel {
  const loops = getNarrativeLoops(visualization);
  let maxScene = 1;
  for (const node of visualization.scene_nodes || []) {
    maxScene = Math.max(maxScene, node.scene_ordinal);
  }

  const rows: HookResolutionRow[] = [];
  const conflicts: HookConflictItem[] = [];
  let resolved = 0;
  let partial = 0;
  let unresolved = 0;
  let conflictCount = 0;

  for (const loop of loops) {
    const open = openSceneOf(loop);
    maxScene = Math.max(maxScene, open);
    const resolvedInfo = resolveHookMainStatus(loop);
    if (resolvedInfo.resolve_scene != null) {
      maxScene = Math.max(maxScene, resolvedInfo.resolve_scene);
    }

    if (resolvedInfo.main_status === "resolved") resolved += 1;
    else if (resolvedInfo.main_status === "partial") partial += 1;
    else unresolved += 1;

    if (resolvedInfo.has_conflict) {
      conflictCount += 1;
      conflicts.push({
        loop_id: loop.loop_id,
        short_title: shortPlainTitle(loop.question || loop.information_gap || loop.loop_id, 12),
        main_status: resolvedInfo.main_status,
        main_label: MAIN_STATUS_LABEL[resolvedInfo.main_status],
        conflict_point: conflictPoint(loop),
        reason: conflictReasonText(loop),
      });
    }

    const mainLabel = MAIN_STATUS_LABEL[resolvedInfo.main_status];
    const lineStyle: HookResolutionLineStyle =
      resolvedInfo.main_status === "resolved"
        ? "solid"
        : resolvedInfo.main_status === "partial"
          ? "dashed"
          : "gray";

    rows.push({
      loop_id: loop.loop_id,
      short_title: shortPlainTitle(loop.question || loop.information_gap || "钩子", 10),
      full_title: loop.question || loop.information_gap || loop.loop_id,
      open_scene: open,
      resolve_scene: resolvedInfo.resolve_scene,
      main_status: resolvedInfo.main_status,
      main_label: mainLabel,
      has_conflict: resolvedInfo.has_conflict,
      conflict_label: resolvedInfo.has_conflict ? "有冲突" : null,
      payoff_type_label: resolvedInfo.payoff_type_label,
      line_style: lineStyle,
      evidence_paragraph_ids: resolvedInfo.evidence_paragraph_ids,
      locate_scene: resolvedInfo.resolve_scene ?? open,
    });
  }

  const stats: HookResolutionChapterStats = {
    established: rows.length,
    resolved,
    partial,
    unresolved,
    conflict: conflictCount,
  };

  return {
    stats,
    verdict: buildChapterVerdict(stats),
    conflicts,
    rows,
    max_scene: Math.max(maxScene, 1),
    empty: rows.length === 0,
  };
}

/** Stats invariant used by tests. */
export function assertMainStatusPartition(stats: HookResolutionChapterStats): boolean {
  return stats.resolved + stats.partial + stats.unresolved === stats.established;
}
