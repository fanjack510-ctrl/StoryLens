/**
 * CHG-20260729-004 — dimension-specific curve node judgments (presentation only).
 * Lenses: plot_progress / reading_tension / emotion / pacing.
 * Does NOT modify composite, hook_payoff, formula_v2, or scores.
 */

import type { JourneySceneNode } from "../../types/readerJourneyVisualization";
import type { ObservationLensId } from "./observationLenses";
import { pacingFitLabel, type PacingFitLabel } from "./observationLenses";

export type DimensionJudgmentLens =
  | "plot_progress"
  | "reading_tension"
  | "emotion"
  | "pacing";

export type DimensionFitLabel = "合适" | "偏弱" | "偏强" | "无法判断" | PacingFitLabel;

export type DimensionNodeJudgment = {
  short_label: string | null;
  full_reason: string | null;
  fit_label: DimensionFitLabel;
  judgment_source: "derived" | "unavailable";
  importance: "high" | "medium" | "low";
  show_persistently: boolean;
};

export type DimensionNodeVisibility = {
  showAboveNode: boolean;
  showOnAxis: boolean;
};

const TARGET_LENSES: DimensionJudgmentLens[] = [
  "plot_progress",
  "reading_tension",
  "emotion",
  "pacing",
];

export function isDimensionJudgmentLens(
  lens: ObservationLensId | null | undefined,
): lens is DimensionJudgmentLens {
  return lens != null && (TARGET_LENSES as string[]).includes(lens);
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function truncateZh(text: string, max: number): string {
  const chars = Array.from(text);
  return chars.length <= max ? text : chars.slice(0, max).join("");
}

function roleKey(node: JourneySceneNode | null | undefined): string {
  return String(node?.scene_role || "").trim().toLowerCase();
}

/** Role bands for plot/tension/emotion fit (presentation; does not alter formula targets). */
const PLOT_ROLE_BANDS: Record<string, [number, number]> = {
  setup: [25, 55],
  escalation: [55, 85],
  investigation: [45, 75],
  reveal: [55, 85],
  climax: [65, 95],
  aftermath: [25, 55],
  transition: [25, 55],
  open_end: [35, 65],
  closed_end: [30, 60],
};

const TENSION_ROLE_BANDS: Record<string, [number, number]> = {
  setup: [30, 60],
  escalation: [55, 85],
  investigation: [50, 80],
  reveal: [45, 75],
  climax: [70, 95],
  aftermath: [25, 55],
  transition: [30, 60],
  open_end: [50, 80],
  closed_end: [25, 55],
};

const EMOTION_ROLE_BANDS: Record<string, [number, number]> = {
  setup: [30, 60],
  escalation: [50, 80],
  investigation: [40, 70],
  reveal: [45, 75],
  climax: [65, 95],
  aftermath: [35, 65],
  transition: [30, 60],
  open_end: [40, 70],
  closed_end: [35, 65],
};

function bandFit(
  score: number | null,
  sceneRole: string,
  bands: Record<string, [number, number]>,
): "合适" | "偏弱" | "偏强" | "无法判断" {
  if (score == null) return "无法判断";
  const band = bands[sceneRole] ?? [40, 70];
  if (score < band[0]) return "偏弱";
  if (score > band[1]) return "偏强";
  return "合适";
}

export function resolveDimensionScore(
  lens: DimensionJudgmentLens,
  node: JourneySceneNode,
): number | null {
  const s = node.scores || ({} as JourneySceneNode["scores"]);
  if (lens === "plot_progress") return num(s.plot_progress);
  if (lens === "reading_tension") return num(s.reading_tension);
  if (lens === "pacing") return num(s.pacing_speed);
  const emotion =
    num(s.emotional_investment) ??
    (num(s.arousal_start) != null && num(s.arousal_end) != null
      ? ((s.arousal_start as number) + (s.arousal_end as number)) / 2
      : num(s.arousal_start) ?? num(s.arousal_end));
  return emotion;
}

export function resolveDimensionFitLabel(
  lens: DimensionJudgmentLens,
  node: JourneySceneNode,
): DimensionFitLabel {
  const role = roleKey(node);
  const score = resolveDimensionScore(lens, node);
  if (lens === "pacing") {
    return pacingFitLabel(score, node.scene_role, num(node.scores?.pacing_fit));
  }
  if (lens === "plot_progress") return bandFit(score, role, PLOT_ROLE_BANDS);
  if (lens === "reading_tension") return bandFit(score, role, TENSION_ROLE_BANDS);
  return bandFit(score, role, EMOTION_ROLE_BANDS);
}

function insightHint(node: JourneySceneNode, lens: DimensionJudgmentLens): string {
  const map = node.dimension_insights;
  if (!map) return "";
  const key =
    lens === "plot_progress"
      ? "plot_progression"
      : lens === "reading_tension"
        ? "reading_tension"
        : lens === "emotion"
          ? "emotional_intensity"
          : "pacing_speed";
  const raw = map[key];
  return typeof raw === "string" ? raw : "";
}

function pickPlotLabel(
  score: number | null,
  prev: number | null,
  role: string,
  insight: string,
): string | null {
  if (score == null) return null;
  const delta = prev != null ? score - prev : 0;

  if (role === "aftermath" || role === "closed_end") return "完成收束";
  if (/反转|逆转|局势/.test(insight) || (role === "reveal" && delta >= 10 && score >= 80)) {
    return "局势反转";
  }
  if (/关系改变|关系变化/.test(insight)) return "关系改变";
  if (/信息揭示|揭晓真相/.test(insight) || (role === "reveal" && delta >= 8 && score < 80)) {
    return "信息揭示";
  }
  if (
    /冲突升级|冲突上升|对抗加剧/.test(insight) ||
    (delta >= 10 && score >= 70 && ["escalation", "climax"].includes(role))
  ) {
    return "冲突升级";
  }
  if (
    /目标明确|目标变化|追查/.test(insight) ||
    (delta >= 12 && score >= 55 && score < 75 && ["escalation", "investigation"].includes(role))
  ) {
    return "目标明确";
  }
  if (/行动启动|开始行动/.test(insight) || (delta >= 8 && score >= 50 && score < 70)) {
    return "行动启动";
  }
  if (role === "setup") return score < 45 ? "信息铺垫" : "信息铺垫";
  if (Math.abs(delta) < 6 && score >= 55) return "推进稳定";
  if (delta <= -12) return "原地停留";
  if (score < 45 || (Math.abs(delta) < 8 && score < 50)) return "推进有限";
  if (delta >= 8) return "行动启动";
  return "推进稳定";
}

function pickTensionLabel(
  score: number | null,
  prev: number | null,
  role: string,
  insight: string,
  node: JourneySceneNode,
): string | null {
  if (score == null) return null;
  const delta = prev != null ? score - prev : 0;
  const payoff = num(node.scores?.payoff);
  const hook = num(node.scores?.hook);

  if (/部分回应/.test(insight)) return "部分回应";
  if (delta <= -8 && delta > -15 && (payoff ?? 0) >= 50) return "部分回应";
  if (/张力回落|完全回应/.test(insight) || (delta <= -15 && (payoff ?? 0) >= 55)) {
    return "张力回落";
  }
  if (/悬置过久|长期无回应/.test(insight) || ((hook ?? 0) >= 65 && (payoff ?? 100) <= 30 && score >= 55)) {
    return "悬置过久";
  }
  if (/悬念强化/.test(insight) || (delta >= 10 && score >= 75)) return "悬念强化";
  if (/风险上升|风险增加/.test(insight) || (delta >= 10 && score >= 55 && score < 75)) {
    return "风险上升";
  }
  if (/危机逼近/.test(insight) || (delta >= 7 && score >= 65 && role === "climax")) {
    return "危机逼近";
  }
  if (/疑问建立|新疑问/.test(insight) || (role === "setup" && (prev == null || delta >= 0))) {
    return "疑问建立";
  }
  if (/期待维持/.test(insight)) return "期待维持";
  if (/信息差扩大/.test(insight) || ((hook ?? 0) - (payoff ?? 0) >= 25 && delta >= 5)) {
    return "信息差扩大";
  }
  if (Math.abs(delta) < 6) return score >= 48 ? "期待维持" : "结果未定";
  if (delta <= -7) return "张力回落";
  if (delta >= 7) return "风险上升";
  return "期待维持";
}

function pickEmotionLabel(
  score: number | null,
  prev: number | null,
  role: string,
  insight: string,
  node: JourneySceneNode,
): string | null {
  if (score == null) return null;
  const delta = prev != null ? score - prev : 0;
  const valenceStart = num(node.scores?.valence_start);
  const valenceEnd = num(node.scores?.valence_end);
  const valenceFlip =
    valenceStart != null &&
    valenceEnd != null &&
    Math.sign(valenceStart) !== Math.sign(valenceEnd) &&
    Math.abs(valenceEnd - valenceStart) >= 0.35;

  if (valenceFlip || /情绪转折/.test(insight)) return "情绪转折";
  if (/愤怒爆发|怒/.test(insight)) return "愤怒爆发";
  if (/悲伤加深|悲/.test(insight)) return "悲伤加深";
  if (/喜悦释放|喜/.test(insight)) return "喜悦释放";
  if (/再次抬升/.test(insight) || (delta >= 8 && prev != null && prev >= 55 && score < 78)) {
    return "再次抬升";
  }
  if (
    /情绪爆发/.test(insight) ||
    delta >= 18 ||
    (score >= 78 && delta >= 10)
  ) {
    return "情绪爆发";
  }
  if (/紧张上升/.test(insight) || (delta >= 10 && score >= 55 && score < 78 && (prev == null || prev < 55))) {
    return "紧张上升";
  }
  if (/情绪积累/.test(insight) || (delta >= 6 && score < 60)) return "情绪积累";
  if (/情绪释放/.test(insight) || ((role === "aftermath" || role === "closed_end") && delta <= -12)) {
    return "情绪释放";
  }
  if (/情绪回落/.test(insight) || delta <= -12) return "情绪回落";
  if (delta <= -7) return role === "aftermath" ? "短暂释放" : "情绪回落";
  if (Math.abs(delta) < 5 && score < 45 && role !== "setup") return "铺垫不足";
  if (role === "setup" || (Math.abs(delta) < 5 && score < 50)) return "情绪铺垫";
  if (Math.abs(delta) < 5) return "变化平稳";
  if (delta > 0) return "情绪积累";
  return "变化平稳";
}

function pickPacingLabel(
  score: number | null,
  prev: number | null,
  role: string,
  insight: string,
): string | null {
  if (score == null) return null;
  const delta = prev != null ? score - prev : 0;

  if (
    (role === "aftermath" || role === "closed_end") &&
    (delta <= -6 || score <= 45 || /收束减速/.test(insight))
  ) {
    return "收束减速";
  }
  if (/再次加速/.test(insight) || (delta >= 10 && prev != null && prev >= 60)) {
    return "再次加速";
  }
  if (/明显加速/.test(insight) || delta >= 18 || (delta >= 14 && score >= 70)) {
    return "明显加速";
  }
  if (/节奏提升/.test(insight) || (delta >= 8 && delta < 14)) return "节奏提升";
  if (/明显减速/.test(insight) || delta <= -15) return "明显减速";
  if (/适度放缓/.test(insight) || (delta <= -7 && delta > -15)) return "适度放缓";
  if (/信息密集/.test(insight) && score >= 65) return "信息密集";
  if (/转换过快/.test(insight) || (score >= 75 && ["transition"].includes(role))) {
    return "转换过快";
  }
  if (/推进偏慢/.test(insight) || (score <= 40 && Math.abs(delta) < 8)) return "推进偏慢";
  if (/留白充分/.test(insight)) return "留白充分";
  if (role === "setup" || (prev == null && Math.abs(delta) < 8)) return "平稳进入";
  if (Math.abs(delta) < 6) return "保持平稳";
  if (delta > 0) return "节奏提升";
  return "适度放缓";
}

function importanceFrom(
  delta: number,
  fit: DimensionFitLabel,
  label: string | null,
): "high" | "medium" | "low" {
  if (!label) return "low";
  const fitCross = fit === "偏强" || fit === "偏弱" || fit === "偏快" || fit === "偏慢";
  if (Math.abs(delta) >= 12 || fitCross) return "high";
  if (Math.abs(delta) >= 7) return "medium";
  if (/爆发|反转|明显加速|明显减速|悬念强化|冲突升级/.test(label)) return "high";
  if (/稳定|平稳|维持|铺垫/.test(label)) return "low";
  return "medium";
}

export function resolveDimensionNodeLabelVisibility(input: {
  sceneCount: number;
  importance: "high" | "medium" | "low";
  isSelected: boolean;
  judgmentSource: "derived" | "unavailable";
}): DimensionNodeVisibility {
  if (input.judgmentSource === "unavailable" && !input.isSelected) {
    return { showAboveNode: false, showOnAxis: false };
  }
  if (input.isSelected) return { showAboveNode: true, showOnAxis: true };
  if (input.sceneCount <= 10) {
    return {
      showAboveNode: input.judgmentSource === "derived",
      showOnAxis: input.importance !== "low",
    };
  }
  if (input.sceneCount <= 20) {
    const persist = input.importance === "high" || input.importance === "medium";
    return { showAboveNode: persist, showOnAxis: input.importance === "high" };
  }
  return {
    showAboveNode: input.importance === "high",
    showOnAxis: input.importance === "high",
  };
}

export function deriveDimensionNodeJudgmentV1(input: {
  dimension: DimensionJudgmentLens;
  currentScene: JourneySceneNode;
  previousScene?: JourneySceneNode | null;
  nextScene?: JourneySceneNode | null;
  sceneCount?: number;
  isSelected?: boolean;
}): DimensionNodeJudgment {
  const { dimension, currentScene, previousScene } = input;
  const role = roleKey(currentScene);
  const score = resolveDimensionScore(dimension, currentScene);
  const prevScore = previousScene ? resolveDimensionScore(dimension, previousScene) : null;
  const fit = resolveDimensionFitLabel(dimension, currentScene);
  const insight = insightHint(currentScene, dimension);
  const delta = score != null && prevScore != null ? score - prevScore : 0;

  let short: string | null = null;
  if (dimension === "plot_progress") short = pickPlotLabel(score, prevScore, role, insight);
  else if (dimension === "reading_tension") {
    short = pickTensionLabel(score, prevScore, role, insight, currentScene);
  } else if (dimension === "emotion") {
    short = pickEmotionLabel(score, prevScore, role, insight, currentScene);
  } else short = pickPacingLabel(score, prevScore, role, insight);

  if (short) short = truncateZh(short, 10);

  const forbiddenCross: Record<DimensionJudgmentLens, RegExp> = {
    plot_progress: /风险上升|情绪爆发|明显加速|钩子/,
    reading_tension: /目标明确|情绪爆发|明显加速|冲突升级/,
    emotion: /冲突升级|明显加速|风险上升/,
    pacing: /冲突升级|情绪爆发|风险上升|目标明确/,
  };
  if (short && forbiddenCross[dimension].test(short)) {
    short = dimension === "pacing" ? "保持平稳" : dimension === "emotion" ? "变化平稳" : null;
  }

  const source: "derived" | "unavailable" = short || fit !== "无法判断" ? "derived" : "unavailable";
  const importance = importanceFrom(delta, fit, short);
  const visibility = resolveDimensionNodeLabelVisibility({
    sceneCount: input.sceneCount ?? 6,
    importance,
    isSelected: Boolean(input.isSelected),
    judgmentSource: source,
  });

  let full: string | null = null;
  if (short) {
    const scoreText = score == null ? "暂无分数" : `当前约 ${Math.round(score)}`;
    full = `${short}；${scoreText}，适配为${fit}。`;
    if (insight) full = `${full}${truncateZh(insight, 48)}`;
  } else if (source === "unavailable") {
    full = "当前节点暂无可靠判断";
  }

  return {
    short_label: short,
    full_reason: full,
    fit_label: fit,
    judgment_source: source,
    importance,
    show_persistently: visibility.showAboveNode,
  };
}

export function buildDimensionJudgmentsForVisualization(
  nodes: JourneySceneNode[],
  lens: DimensionJudgmentLens,
  selectedOrdinal: number | null,
): Map<number, DimensionNodeJudgment> {
  const ordered = [...nodes]
    .filter((n) => n.include_in_main_curve !== false && n.role !== "beat" && n.node_type !== "beat")
    .sort((a, b) => a.scene_ordinal - b.scene_ordinal);
  const map = new Map<number, DimensionNodeJudgment>();
  for (let i = 0; i < ordered.length; i += 1) {
    const curr = ordered[i];
    map.set(
      curr.scene_ordinal,
      deriveDimensionNodeJudgmentV1({
        dimension: lens,
        currentScene: curr,
        previousScene: i > 0 ? ordered[i - 1] : null,
        nextScene: i + 1 < ordered.length ? ordered[i + 1] : null,
        sceneCount: ordered.length,
        isSelected: selectedOrdinal === curr.scene_ordinal,
      }),
    );
  }
  return map;
}
