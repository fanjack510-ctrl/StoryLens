/** Bind observation lens → field key + user label + node value (same number everywhere). */

import type {
  JourneyCurvePoint,
  JourneyPhaseVisualization,
  JourneySceneNode,
  ReaderJourneyVisualization,
} from "../../types/readerJourneyVisualization";
import { resolveMetricValue } from "./journeyChartScales";
import {
  buildLensChartLines,
  getObservationLens,
  nodeScoreRecord,
  pacingFitLabel,
  type ObservationLensId,
  type PacingFitLabel,
} from "./observationLenses";
import { formatJourneyScore } from "./journeyUiLabels";
import { getScenePayoffClaim } from "./narrativeLoopView";

export type LensMetricBinding = {
  fieldKey: string;
  labelZh: string;
  value: number | null;
  /** Extra paired fields (hook/payoff, arousal/valence, pacing_speed/fit). */
  secondary?: Array<{ fieldKey: string; labelZh: string; value: number | null; text?: string }>;
};

/** V2 native / fixture presentation — never surface engagement / 阅读牵引. */
export function usesReadingMomentumTerminology(
  visualization: ReaderJourneyVisualization | null | undefined,
): boolean {
  if (!visualization) return false;
  const mode = visualization.calibration_status?.source_mode;
  if (mode === "v2_native" || mode === "local_fixture") return true;
  const contract = visualization.calibration_status?.scene_contract_version;
  if (typeof contract === "string" && contract.startsWith("2.")) return true;
  // Observation-lens UI always treats composite primary as reading_momentum.
  return true;
}

export function readingMomentumLabelZh(
  visualization: ReaderJourneyVisualization | null | undefined,
): string {
  return usesReadingMomentumTerminology(visualization) ? "阅读动力" : "阅读牵引";
}

export function resolveNodeFieldValue(
  node: JourneySceneNode,
  fieldKey: string,
): number | null {
  const scores = nodeScoreRecord(node);
  const raw = scores[fieldKey];
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (fieldKey === "arousal") {
    const avg =
      averageDefined(scores.arousal_start, scores.arousal_end) ??
      averageDefined(node.scores?.arousal_start, node.scores?.arousal_end);
    return avg ?? null;
  }
  if (fieldKey === "valence") {
    const avg = averageDefined(scores.valence_start, scores.valence_end);
    return avg ?? null;
  }
  return null;
}

function averageDefined(...values: Array<number | undefined | null>): number | undefined {
  const nums = values.filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  if (!nums.length) return undefined;
  return nums.reduce((a, b) => a + b, 0) / nums.length;
}

/** Single source of truth for phase card / caption / polyline / right panel. */
export function resolveLensMetricBinding(
  visualization: ReaderJourneyVisualization,
  lensId: ObservationLensId,
  node: JourneySceneNode | null | undefined,
): LensMetricBinding {
  const lens = getObservationLens(lensId);
  const momentumLabel = readingMomentumLabelZh(visualization);

  if (lens.id === "composite") {
    return {
      fieldKey: "reading_momentum",
      labelZh: momentumLabel,
      value: node ? resolveNodeFieldValue(node, "reading_momentum") : null,
    };
  }
  if (lens.id === "plot_progress") {
    return {
      fieldKey: "plot_progress",
      labelZh: "剧情推进",
      value: node ? resolveNodeFieldValue(node, "plot_progress") : null,
    };
  }
  if (lens.id === "reading_tension") {
    return {
      fieldKey: "reading_tension",
      labelZh: "阅读张力",
      value: node ? resolveNodeFieldValue(node, "reading_tension") : null,
    };
  }
  if (lens.id === "emotion") {
    const arousal = node ? resolveNodeFieldValue(node, "arousal") : null;
    const valence = node ? resolveNodeFieldValue(node, "valence") : null;
    return {
      fieldKey: "arousal",
      labelZh: "情绪强度",
      value: arousal,
      secondary: [
        {
          fieldKey: "valence",
          labelZh: "情绪正负",
          value: valence,
        },
      ],
    };
  }
  if (lens.id === "hook_payoff") {
    const hook = node ? resolveNodeFieldValue(node, "hook") : null;
    const payoff = node ? resolveNodeFieldValue(node, "payoff") : null;
    const claim = node ? getScenePayoffClaim(visualization, node.scene_ordinal) : null;
    let payoffText = "本场回报 —";
    if (payoff != null) {
      if (claim && !claim.deterministic) {
        payoffText = `本场回报 ${Math.round(payoff)} · ${claim.label}`;
      } else if (claim?.claim === "full") {
        payoffText = `本场回报 ${Math.round(payoff)} · 有效兑现`;
      } else if (claim?.claim === "partial" || (claim == null && payoff >= 40 && payoff < 70)) {
        payoffText = `本场回报 ${Math.round(payoff)} · 部分兑现`;
      } else if (claim?.claim === "none" || payoff < 40) {
        payoffText = `本场回报 ${Math.round(payoff)} · 未兑现`;
      } else if (payoff >= 70) {
        // Score-only high payoff without deterministic claim — never assert 有效兑现.
        payoffText = `本场回报 ${Math.round(payoff)} · 关系待核对`;
      } else {
        payoffText = `本场回报 ${Math.round(payoff)}`;
      }
    }
    return {
      fieldKey: "hook",
      labelZh: "钩子强度",
      value: hook,
      secondary: [
        {
          fieldKey: "payoff",
          labelZh: "本场回报强度",
          value: payoff,
          text: payoffText,
        },
      ],
    };
  }
  // pacing: speed + fit are distinct — never one fused score
  const speed = node ? resolveNodeFieldValue(node, "pacing_speed") : null;
  const fitScore = node ? resolveNodeFieldValue(node, "pacing_fit") : null;
  const fitLabel: PacingFitLabel | null =
    speed == null
      ? null
      : pacingFitLabel(speed, node?.scene_role, fitScore);
  return {
    fieldKey: "pacing_speed",
    labelZh: "节奏速度",
    value: speed,
    secondary: [
      {
        fieldKey: "pacing_fit",
        labelZh: "节奏契合",
        value: fitScore,
        text: fitLabel ? `契合 ${fitLabel}` : "契合 —",
      },
    ],
  };
}

export function formatLensBindingCaption(binding: LensMetricBinding): string {
  const primary =
    binding.value == null
      ? `${binding.labelZh} —`
      : `${binding.labelZh} ${formatJourneyScore(binding.value)}`;
  if (!binding.secondary?.length) return primary;
  const extras = binding.secondary.map((item) => {
    if (item.text) return item.text;
    if (item.value == null) return `${item.labelZh} —`;
    return `${item.labelZh} ${formatJourneyScore(item.value)}`;
  });
  return [primary, ...extras].join(" · ");
}

export function formatLensPhaseScoreLabel(
  visualization: ReaderJourneyVisualization,
  lensId: ObservationLensId,
  value: number | null | undefined,
): string {
  const binding = resolveLensMetricBinding(visualization, lensId, null);
  if (lensId === "pacing") {
    return value == null || !Number.isFinite(value)
      ? "节奏速度 —"
      : `节奏速度 ${formatJourneyScore(value)}`;
  }
  if (lensId === "emotion") {
    return value == null || !Number.isFinite(value)
      ? "情绪强度 —"
      : `情绪强度 ${formatJourneyScore(value)}`;
  }
  if (lensId === "hook_payoff") {
    return value == null || !Number.isFinite(value)
      ? "平均钩子 —"
      : `平均钩子 ${formatJourneyScore(value)}`;
  }
  return value == null || !Number.isFinite(value)
    ? `${binding.labelZh} —`
    : `${binding.labelZh} ${formatJourneyScore(value)}`;
}

/** Phase average from the same series the chart polyline uses. */
export function phaseAverageForLens(
  visualization: ReaderJourneyVisualization,
  lensId: ObservationLensId,
  phase: JourneyPhaseVisualization,
): number | null {
  const lines = buildLensChartLines(visualization, lensId);
  const primary = lines[0]?.series ?? [];
  const values: number[] = [];
  for (let ordinal = phase.start_scene_ordinal; ordinal <= phase.end_scene_ordinal; ordinal += 1) {
    const point = primary.find((item: JourneyCurvePoint) => item.scene_ordinal === ordinal);
    const resolved = resolveMetricValue(point);
    if (resolved != null && Number.isFinite(resolved)) values.push(resolved);
  }
  if (!values.length) return null;
  return values.reduce((sum, item) => sum + item, 0) / values.length;
}

export function seriesValueAtOrdinal(
  visualization: ReaderJourneyVisualization,
  lensId: ObservationLensId,
  sceneOrdinal: number,
): number | null {
  const lines = buildLensChartLines(visualization, lensId);
  const point = lines[0]?.series.find((item) => item.scene_ordinal === sceneOrdinal);
  const resolved = resolveMetricValue(point);
  return resolved == null || !Number.isFinite(resolved) ? null : resolved;
}
