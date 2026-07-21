/** Narrative helpers for why a scene peaks/valleys (v2 inspector). */

import type { JourneySceneNode, ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import { primaryBandLabelForScene } from "./diagnosisBandModel";

export type SceneNarrative = {
  whyHighOrLow: string;
  narrativeTechnique: string;
  priorSetup: string;
  laterPayoff: string;
};

export function buildSceneNarrative(
  visualization: ReaderJourneyVisualization,
  node: JourneySceneNode,
): SceneNarrative {
  const ordinal = node.scene_ordinal;
  const prev = visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal - 1);
  const next = visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal + 1);
  const momentum =
    node.scores.reading_momentum ?? node.engagement.engagement_score ?? 0;
  const label = primaryBandLabelForScene({
    scene_ordinal: ordinal,
    primary_diagnosis: node.primary_diagnosis,
    secondary_diagnoses: node.secondary_diagnoses,
    positive_mechanism: node.positive_mechanism,
    data_quality_issue: node.data_quality_issue,
    reading_momentum: momentum,
    plot_progress: node.scores.plot_progress,
  });

  const peakish = momentum >= 70;
  const whyHighOrLow = peakish
    ? `为什么高：本场「${label}」，综合阅读约 ${Math.round(momentum)}；${node.scene_value_summary}`
    : `为什么低/平：本场「${label}」，综合阅读约 ${Math.round(momentum)}；${node.scene_value_summary}`;

  const techniqueParts = node.techniques
    .slice(0, 2)
    .map((t) => t.name || t.code)
    .filter(Boolean);
  const narrativeTechnique = techniqueParts.length
    ? `使用了什么叙事方式：${techniqueParts.join("、")}`
    : node.positive_mechanism
      ? `使用了什么叙事方式：${node.positive_mechanism}`
      : `使用了什么叙事方式：${node.dominant_emotion || "情绪/信息推进"}（见技法与证据）`;

  const priorSetup = prev
    ? `前面如何蓄积：S${prev.scene_ordinal}「${prev.scene_value_summary}」；钩子 ${prev.scores.hook ?? "—"} → 本场承接。`
    : "前面如何蓄积：本章开场，蓄积来自本场自身铺垫。";

  const laterPayoff = next
    ? `后面如何兑现：S${next.scene_ordinal}「${next.scene_value_summary}」；本场 hook ${node.scores.hook ?? "—"} / payoff ${node.scores.payoff ?? "—"}。`
    : `后面如何兑现：章末场，回报看本场 payoff ${node.scores.payoff ?? "—"} 与开放问题。`;

  return { whyHighOrLow, narrativeTechnique, priorSetup, laterPayoff };
}
