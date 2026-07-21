/** Chapter-level summary bullets (max 3) for Reader Journey header. */

import type { ReaderJourneyVisualization } from "../../types/readerJourneyVisualization";
import {
  primaryBandLabelForScene,
  type SceneDiagnosisLike,
} from "./diagnosisBandModel";

export type ChapterSummaryBullet = {
  kind: "advantage" | "problem" | "key_span";
  text: string;
};

function nodeMomentum(visualization: ReaderJourneyVisualization, ordinal: number): number {
  const node = visualization.scene_nodes.find((n) => n.scene_ordinal === ordinal);
  if (!node) return 0;
  const scores = node.scores as Record<string, number | undefined>;
  return (
    scores.reading_momentum ??
    node.engagement?.engagement_score ??
    scores.curiosity ??
    0
  );
}

export function buildChapterSummaryBullets(
  visualization: ReaderJourneyVisualization,
  diagnoses: SceneDiagnosisLike[] = [],
): ChapterSummaryBullet[] {
  const nodes = visualization.scene_nodes.filter((n) => n.role !== "beat");
  if (!nodes.length) return [];

  const byOrdinal = new Map(diagnoses.map((d) => [d.scene_ordinal, d]));
  let peak = nodes[0];
  let valley = nodes[0];
  for (const node of nodes) {
    if (nodeMomentum(visualization, node.scene_ordinal) >
      nodeMomentum(visualization, peak.scene_ordinal)) {
      peak = node;
    }
    if (nodeMomentum(visualization, node.scene_ordinal) <
      nodeMomentum(visualization, valley.scene_ordinal)) {
      valley = node;
    }
  }

  const peakDiag = byOrdinal.get(peak.scene_ordinal);
  const valleyDiag = byOrdinal.get(valley.scene_ordinal);
  const peakLabel = peakDiag ? primaryBandLabelForScene(peakDiag) : "表现有效";
  const valleyLabel = valleyDiag ? primaryBandLabelForScene(valleyDiag) : "推进偏弱";

  const payoffScene = nodes.find((n) => (n.scores?.payoff ?? 0) >= 70);
  const hookScene = nodes.find((n) => (n.scores?.hook ?? 0) >= 70);

  const bullets: ChapterSummaryBullet[] = [];
  bullets.push({
    kind: "advantage",
    text: `最大优势：S${peak.scene_ordinal} 形成本章高点（${peakLabel}），阅读动力约 ${Math.round(
      nodeMomentum(visualization, peak.scene_ordinal),
    )}。${peak.scene_value_summary ? `机制：${peak.scene_value_summary}` : ""}`.trim(),
  });

  const problemText =
    valleyLabel === "切分异常"
      ? `主要问题：S${valley.scene_ordinal} 存在切分异常（数据质量），不归因于作品节奏。`
      : `主要问题：S${valley.scene_ordinal} 表现为${valleyLabel}，需回看证据与前后蓄积。`;
  bullets.push({ kind: "problem", text: problemText });

  const start = Math.min(peak.scene_ordinal, payoffScene?.scene_ordinal ?? peak.scene_ordinal);
  const end = Math.max(peak.scene_ordinal, payoffScene?.scene_ordinal ?? peak.scene_ordinal);
  const spanText =
    hookScene && payoffScene && payoffScene.scene_ordinal > hookScene.scene_ordinal
      ? `关键区段：S${hookScene.scene_ordinal}—S${payoffScene.scene_ordinal} 从钩子建立到兑现；S${valley.scene_ordinal} 若为余波/aftermath 则不宜直接判拖沓。`
      : `关键区段：S${start}—S${end} 承载本章主张力与回报；谷值在 S${valley.scene_ordinal}（${valleyLabel}）。`;
  bullets.push({ kind: "key_span", text: spanText });

  return bullets.slice(0, 3);
}
