/**
 * Hook/payoff lens semantics — presentation only.
 * Does not retune weights, formulas, or diagnosis thresholds.
 */

import type {
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import type { ObservationLensId } from "./observationLenses";
import { nodeScoreRecord } from "./observationLenses";
import type { DiagnosisBandLabel, SceneDiagnosisLike } from "./diagnosisBandModel";
import { mapDiagnosisCodeToBandLabel, primaryBandLabelForScene } from "./diagnosisBandModel";
import { formatPayoffClaimLabel, getScenePayoffClaim } from "./narrativeLoopView";

export const HOOK_STRENGTH_LABEL = "钩子强度";
export const PAYOFF_STRENGTH_LABEL = "本场回报强度";
export const PAYOFF_NOT_CUMULATIVE_HINT =
  "回报表示本场对前文问题的兑现强度，不是累计完成比例。";

export type HookPayoffDataStatus = "v2_native" | "legacy" | "missing";

export type QuestionLifecycleView = {
  question_id: string;
  question_text: string;
  setup_scene: number;
  development_scenes: number[];
  payoff_scene: number | null;
  status: string;
  strength?: number;
};

export type HookPayoffSceneSummary = {
  sceneOrdinal: number;
  hook: number | null;
  payoff: number | null;
  lifecycleStatusLabel: string;
  payoffPlainText: string;
  dataStatus: HookPayoffDataStatus;
};

/** Diagnosis labels allowed as primary band on hook/payoff lens. */
export const HOOK_PAYOFF_PRIMARY_BAND_LABELS = new Set<DiagnosisBandLabel>([
  "钩子建立",
  "钩子不足",
  "兑现延迟",
  "空钩子",
  "有效兑现",
  "突然揭晓",
  "数据不足",
  "旧版数据",
  "辅助节拍",
  "未发现明显异常",
  "表现有效",
]);

const HOOK_PAYOFF_CODE_PRIORITY = new Set([
  "weak_hook",
  "empty_hook",
  "delayed_payoff",
  "abrupt_reveal",
  "effective_payoff",
  "low_confidence",
  "scene_boundary_anomaly",
]);

export function resolveHookPayoffDataStatus(
  visualization: ReaderJourneyVisualization,
  node: JourneySceneNode | null | undefined,
): HookPayoffDataStatus {
  const mode = visualization.calibration_status?.source_mode;
  const contract = String(visualization.calibration_status?.scene_contract_version || "");
  if (mode === "v2_native" || contract.startsWith("2.")) {
    if (!node) return "missing";
    const scores = node.scores as Record<string, number | undefined>;
    if (scores.hook == null && scores.payoff == null) return "missing";
    return "v2_native";
  }
  if (mode === "legacy_adapter" || contract.startsWith("1.")) return "legacy";
  if (!node) return "missing";
  const scores = node.scores as Record<string, number | undefined>;
  if (scores.hook == null && scores.payoff == null) return "missing";
  return mode === "v2_native" ? "v2_native" : "legacy";
}

export function payoffPlainLanguage(payoff: number | null | undefined): string {
  if (payoff == null || !Number.isFinite(payoff)) return "本场回报数据不足。";
  if (payoff <= 0) return "本场未提供有效兑现。";
  if (payoff < 40) return "本场提供少量线索或部分回答，核心问题仍未兑现。";
  if (payoff < 70) return "本场完成部分兑现，核心问题仍未完全回收。";
  // High score alone is not a deterministic 有效兑现 claim.
  return "本场回报分数较高，需结合回报实体与证据核对。";
}

export function lifecycleStatusLabelZh(status: string | null | undefined): string {
  switch (status) {
    case "open":
      return "已建立";
    case "progressing":
      return "推进中";
    case "paid_off":
      return "已兑现";
    case "abandoned":
      return "已遗弃";
    case "overdue":
      return "已逾期";
    case "partial":
      return "部分兑现";
    case "none":
      return "未建立";
    case "missing":
      return "数据不足";
    case "legacy":
      return "旧版数据";
    default:
      return status?.trim() ? status : "数据不足";
  }
}

export function getQuestionLifecycle(
  visualization: ReaderJourneyVisualization,
): QuestionLifecycleView[] {
  const raw =
    (visualization as { question_lifecycle?: QuestionLifecycleView[] }).question_lifecycle ??
    (visualization as { v2_question_lifecycle?: QuestionLifecycleView[] }).v2_question_lifecycle ??
    [];
  if (!Array.isArray(raw)) return [];
  return raw.filter((item) => item && typeof item.question_id === "string");
}

export function questionsForScene(
  lifecycle: QuestionLifecycleView[],
  sceneOrdinal: number,
): QuestionLifecycleView[] {
  return lifecycle.filter((item) => {
    if (item.setup_scene === sceneOrdinal) return true;
    if (item.payoff_scene === sceneOrdinal) return true;
    return (item.development_scenes || []).includes(sceneOrdinal);
  });
}

export function sceneRoleInLifecycle(
  item: QuestionLifecycleView,
  sceneOrdinal: number,
): "建立" | "强化" | "推进" | "部分兑现" | "完成兑现" | "关联" {
  if (item.setup_scene === sceneOrdinal) return "建立";
  if (item.payoff_scene === sceneOrdinal) {
    return item.status === "paid_off" ? "完成兑现" : "部分兑现";
  }
  if ((item.development_scenes || []).includes(sceneOrdinal)) {
    return item.status === "progressing" ? "推进" : "强化";
  }
  return "关联";
}

export function buildHookPayoffSceneSummary(
  visualization: ReaderJourneyVisualization,
  node: JourneySceneNode | null | undefined,
): HookPayoffSceneSummary | null {
  if (!node) return null;
  const scores = nodeScoreRecord(node);
  const hook = typeof scores.hook === "number" && Number.isFinite(scores.hook) ? scores.hook : null;
  const payoff =
    typeof scores.payoff === "number" && Number.isFinite(scores.payoff) ? scores.payoff : null;
  const dataStatus = resolveHookPayoffDataStatus(visualization, node);
  const related = questionsForScene(getQuestionLifecycle(visualization), node.scene_ordinal);
  const primary = related[0];
  let lifecycleStatusLabel = "未建立";
  if (dataStatus === "legacy") lifecycleStatusLabel = "旧版数据";
  else if (dataStatus === "missing") lifecycleStatusLabel = "数据不足";
  else if (primary) lifecycleStatusLabel = lifecycleStatusLabelZh(primary.status);
  else if (payoff != null && payoff >= 70) lifecycleStatusLabel = "已兑现";
  else if (payoff != null && payoff >= 40) lifecycleStatusLabel = "部分兑现";
  else if (hook != null && hook >= 40) lifecycleStatusLabel = "已建立";
  else lifecycleStatusLabel = "未建立";

  return {
    sceneOrdinal: node.scene_ordinal,
    hook,
    payoff,
    lifecycleStatusLabel,
    payoffPlainText: formatPayoffClaimLabel(getScenePayoffClaim(visualization, node.scene_ordinal), payoff),
    dataStatus,
  };
}

export function formatHookPayoffSceneCaption(summary: HookPayoffSceneSummary): string {
  const hookText = summary.hook == null ? "钩子 —" : `钩子 ${Math.round(summary.hook)}`;
  const payoffText =
    summary.payoff == null ? "回报 —" : `回报 ${Math.round(summary.payoff)}`;
  return `场景 S${String(summary.sceneOrdinal).padStart(2, "0")} · ${hookText} · ${payoffText} · ${summary.lifecycleStatusLabel}`;
}

export function hookPayoffCombinationExplanation(
  hook: number | null | undefined,
  payoff: number | null | undefined,
): string {
  if (hook == null || payoff == null) {
    return "本场钩子/回报数据不足，暂不能给出组合解释。";
  }
  const highHook = hook >= 65;
  const lowHook = hook < 40;
  const highPayoff = payoff >= 65;
  const risingPayoff = payoff >= 40 && payoff < 65;
  const lowPayoff = payoff < 40;

  if (highHook && lowPayoff) {
    return "本场主要建立或强化阅读期待，核心问题尚未得到回答。";
  }
  if (highHook && risingPayoff) {
    return "本场在兑现旧问题的同时继续建立新的阅读期待。";
  }
  if (highHook && highPayoff) {
    return "本场完成阶段性揭晓，同时引出新的未决问题。";
  }
  if (lowHook && highPayoff) {
    return "本场主要承担解释、回收或结果兑现。";
  }
  if (lowHook && lowPayoff) {
    return "本场缺少明确的新期待和兑现，需要结合场景任务判断是否为有效过渡。";
  }
  return "本场钩子与回报处于中位，宜结合问题生命周期判断推进或兑现角色。";
}

export function primaryBandLabelForHookPayoffLens(diag: SceneDiagnosisLike): DiagnosisBandLabel {
  if (diag.role === "beat" || diag.node_type === "beat" || diag.include_in_main_curve === false) {
    return "辅助节拍";
  }
  if (diag.insufficientData) return "数据不足";
  if (diag.legacyUncalibrated) return "旧版数据";

  const secondary = diag.secondary_diagnoses ?? [];
  const candidates = [diag.primary_diagnosis, ...secondary].filter(Boolean) as string[];
  for (const code of candidates) {
    if (!HOOK_PAYOFF_CODE_PRIORITY.has(code) && code !== diag.positive_mechanism) {
      // Prefer hook/payoff codes; skip plot/tension/pacing primaries.
      if (
        code.startsWith("plot_") ||
        code.startsWith("pacing_") ||
        code.includes("tension") ||
        code.includes("curiosity") ||
        code.includes("emotional") ||
        code === "empty_fast_pacing" ||
        code === "weak_progress" ||
        code === "information_overload"
      ) {
        continue;
      }
    }
    const mapped = mapDiagnosisCodeToBandLabel(code);
    if (mapped && HOOK_PAYOFF_PRIMARY_BAND_LABELS.has(mapped)) return mapped;
  }

  // Positive mechanism may be effective_payoff / hook setup.
  if (diag.positive_mechanism) {
    const mapped = mapDiagnosisCodeToBandLabel(diag.positive_mechanism);
    if (mapped && HOOK_PAYOFF_PRIMARY_BAND_LABELS.has(mapped)) return mapped;
    if (diag.positive_mechanism === "effective_payoff") return "有效兑现";
  }

  const fallback = primaryBandLabelForScene(diag);
  if (HOOK_PAYOFF_PRIMARY_BAND_LABELS.has(fallback)) return fallback;
  // Other-lens diagnoses move to 其他诊断 — band shows neutral / data hint.
  if (!diag.primary_diagnosis) return "未发现明显异常";
  return "未发现明显异常";
}

export function otherDiagnosesForHookPayoffLens(diag: SceneDiagnosisLike): string[] {
  const labels: string[] = [];
  const primary = primaryBandLabelForScene(diag);
  if (!HOOK_PAYOFF_PRIMARY_BAND_LABELS.has(primary) && primary !== "未发现明显异常") {
    labels.push(primary);
  }
  for (const code of diag.secondary_diagnoses ?? []) {
    const mapped = mapDiagnosisCodeToBandLabel(code);
    if (mapped && !HOOK_PAYOFF_PRIMARY_BAND_LABELS.has(mapped)) labels.push(mapped);
  }
  return [...new Set(labels)];
}

export function phaseHookPayoffAverages(
  visualization: ReaderJourneyVisualization,
  phase: { start_scene_ordinal: number; end_scene_ordinal: number },
): { avgHook: number | null; avgPayoff: number | null; statusLabel: string } {
  const hooks: number[] = [];
  const payoffs: number[] = [];
  for (const node of visualization.scene_nodes) {
    if (isBeatNodeForLens(node)) continue;
    if (
      node.scene_ordinal < phase.start_scene_ordinal ||
      node.scene_ordinal > phase.end_scene_ordinal
    ) {
      continue;
    }
    const scores = nodeScoreRecord(node);
    if (typeof scores.hook === "number" && Number.isFinite(scores.hook)) hooks.push(scores.hook);
    if (typeof scores.payoff === "number" && Number.isFinite(scores.payoff)) {
      payoffs.push(scores.payoff);
    }
  }
  const avgHook = hooks.length ? hooks.reduce((a, b) => a + b, 0) / hooks.length : null;
  const avgPayoff = payoffs.length
    ? payoffs.reduce((a, b) => a + b, 0) / payoffs.length
    : null;
  let statusLabel = "推进中";
  if ((avgPayoff ?? 0) >= 65 && (avgHook ?? 0) < 50) statusLabel = "兑现中";
  else if ((avgPayoff ?? 0) >= 65 && (avgHook ?? 0) >= 50) statusLabel = "已回收";
  else if ((avgHook ?? 0) >= 65 && (avgPayoff ?? 0) < 40) statusLabel = "建立中";
  else if ((avgHook ?? 0) >= 45) statusLabel = "推进中";
  return { avgHook, avgPayoff, statusLabel };
}

export function buildHookPayoffChapterBullets(
  visualization: ReaderJourneyVisualization,
): Array<{ kind: "advantage" | "problem" | "key_span"; text: string }> {
  const nodes = visualization.scene_nodes.filter((n) => !isBeatNodeForLens(n));
  if (!nodes.length) return [];
  const lifecycle = getQuestionLifecycle(visualization);
  let setupScene = nodes[0];
  let payoffScene = nodes[0];
  for (const node of nodes) {
    const scores = nodeScoreRecord(node);
    const setupScores = nodeScoreRecord(setupScene);
    const payoffScores = nodeScoreRecord(payoffScene);
    if ((scores.hook ?? 0) > (setupScores.hook ?? 0)) setupScene = node;
    if ((scores.payoff ?? 0) > (payoffScores.payoff ?? 0)) payoffScene = node;
  }
  const openCount = lifecycle.filter((q) =>
    ["open", "progressing", "overdue"].includes(q.status),
  ).length;
  const paidCount = lifecycle.filter((q) => q.status === "paid_off").length;
  const bullets = [
    {
      kind: "advantage" as const,
      text: `主要钩子建立区段：S${setupScene.scene_ordinal} 钩子约 ${Math.round(
        nodeScoreRecord(setupScene).hook ?? 0,
      )}，本章问题多在此前后被建立或强化。`,
    },
    {
      kind: "key_span" as const,
      text: `主要兑现区段：S${payoffScene.scene_ordinal} 本场回报约 ${Math.round(
        nodeScoreRecord(payoffScene).payoff ?? 0,
      )}；已兑现问题 ${paidCount} 个。`,
    },
    {
      kind: "problem" as const,
      text:
        openCount > 0
          ? `未兑现或延迟兑现：仍有 ${openCount} 个问题处于开放/推进/逾期状态。`
          : "未兑现或延迟兑现：当前生命周期内未见明显开放问题。",
    },
  ];
  return bullets.slice(0, 3);
}

export function isHookPayoffLens(lensId: ObservationLensId | null | undefined): boolean {
  return lensId === "hook_payoff";
}

function isBeatNodeForLens(node: JourneySceneNode): boolean {
  if (node.role === "beat") return true;
  if (node.node_type === "beat") return true;
  if (node.include_in_main_curve === false) return true;
  return false;
}
