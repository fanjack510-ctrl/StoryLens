/** Significant segment rise/fall markers — only label clear deltas. */

export type SegmentMarkerKind =
  | "冲突升级"
  | "新信息揭晓"
  | "情绪爆发"
  | "钩子建立"
  | "有效兑现"
  | "推进停滞"
  | "节奏拖慢"
  | "张力下降"
  | "钩子失效"
  | "表达阻力";

export type SegmentMarker = {
  fromOrdinal: number;
  toOrdinal: number;
  direction: "up" | "down";
  label: SegmentMarkerKind;
  delta: number;
};

export type SegmentSample = {
  scene_ordinal: number;
  reading_momentum?: number | null;
  plot_progress?: number | null;
  reading_tension?: number | null;
  hook?: number | null;
  payoff?: number | null;
  pacing_speed?: number | null;
  clarity?: number | null;
  information_gain?: number | null;
  arousal?: number | null;
};

const RISE_THRESHOLD = 12;
const FALL_THRESHOLD = -12;

export function buildSegmentMarkers(samples: SegmentSample[]): SegmentMarker[] {
  const ordered = [...samples].sort((a, b) => a.scene_ordinal - b.scene_ordinal);
  const markers: SegmentMarker[] = [];
  for (let i = 1; i < ordered.length; i += 1) {
    const prev = ordered[i - 1];
    const curr = ordered[i];
    const momentumDelta =
      (curr.reading_momentum ?? 0) - (prev.reading_momentum ?? 0);
    if (Math.abs(momentumDelta) < Math.abs(RISE_THRESHOLD)) continue;

    if (momentumDelta >= RISE_THRESHOLD) {
      const label = pickRiseLabel(prev, curr);
      if (label) {
        markers.push({
          fromOrdinal: prev.scene_ordinal,
          toOrdinal: curr.scene_ordinal,
          direction: "up",
          label,
          delta: momentumDelta,
        });
      }
    } else if (momentumDelta <= FALL_THRESHOLD) {
      const label = pickFallLabel(prev, curr);
      if (label) {
        markers.push({
          fromOrdinal: prev.scene_ordinal,
          toOrdinal: curr.scene_ordinal,
          direction: "down",
          label,
          delta: momentumDelta,
        });
      }
    }
  }
  return markers;
}

function pickRiseLabel(prev: SegmentSample, curr: SegmentSample): SegmentMarkerKind | null {
  const payoffDelta = (curr.payoff ?? 0) - (prev.payoff ?? 0);
  const hookDelta = (curr.hook ?? 0) - (prev.hook ?? 0);
  const infoDelta = (curr.information_gain ?? 0) - (prev.information_gain ?? 0);
  const arousalDelta = (curr.arousal ?? 0) - (prev.arousal ?? 0);
  const tensionDelta = (curr.reading_tension ?? 0) - (prev.reading_tension ?? 0);
  if (payoffDelta >= 15) return "有效兑现";
  if (hookDelta >= 15) return "钩子建立";
  if (infoDelta >= 15) return "新信息揭晓";
  if (arousalDelta >= 18) return "情绪爆发";
  if (tensionDelta >= 12) return "冲突升级";
  return "冲突升级";
}

function pickFallLabel(prev: SegmentSample, curr: SegmentSample): SegmentMarkerKind | null {
  const plotDelta = (curr.plot_progress ?? 0) - (prev.plot_progress ?? 0);
  const pacingDelta = (curr.pacing_speed ?? 0) - (prev.pacing_speed ?? 0);
  const tensionDelta = (curr.reading_tension ?? 0) - (prev.reading_tension ?? 0);
  const hookDelta = (curr.hook ?? 0) - (prev.hook ?? 0);
  const clarityDelta = (curr.clarity ?? 50) - (prev.clarity ?? 50);
  if (plotDelta <= -12) return "推进停滞";
  if (pacingDelta <= -12) return "节奏拖慢";
  if (tensionDelta <= -12) return "张力下降";
  if (hookDelta <= -15) return "钩子失效";
  if (clarityDelta <= -12) return "表达阻力";
  return "推进停滞";
}
