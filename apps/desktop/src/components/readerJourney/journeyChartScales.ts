import type { JourneyCurvePoint } from "../../types/readerJourneyVisualization";
import {
  CHART_PAD,
  DEFAULT_Y_DOMAIN_MODE,
  Y_TICKS_FIXED,
  type YDomainMode,
} from "./journeyVisualizationConfig";

export type ResolvedMetricValue = number | null;

export type DataRangeWarning = {
  scene_ordinal: number;
  value: number;
  kind: "below_0" | "above_100";
};

/** Resolve a curve point; missing/NaN → null (line break). Never coerce null to 0. */
export function resolveMetricValue(
  point: JourneyCurvePoint | undefined | null,
): ResolvedMetricValue {
  if (!point) return null;
  if (typeof point.value === "number" && Number.isFinite(point.value)) {
    return point.value;
  }
  if (
    typeof point.start === "number" &&
    Number.isFinite(point.start) &&
    typeof point.end === "number" &&
    Number.isFinite(point.end)
  ) {
    return (point.start + point.end) / 2;
  }
  if (typeof point.end === "number" && Number.isFinite(point.end)) return point.end;
  if (typeof point.start === "number" && Number.isFinite(point.start)) return point.start;
  return null;
}

/** Legacy helper used by non-chart call sites that still expect a number. */
export function metricValueOrZero(point: {
  value?: number;
  start?: number;
  end?: number;
}): number {
  const resolved = resolveMetricValue(point as JourneyCurvePoint);
  return resolved ?? 0;
}

export function collectDataWarnings(series: JourneyCurvePoint[]): DataRangeWarning[] {
  const warnings: DataRangeWarning[] = [];
  for (const point of series) {
    const value = resolveMetricValue(point);
    if (value == null) continue;
    if (value < 0) {
      warnings.push({ scene_ordinal: point.scene_ordinal, value, kind: "below_0" });
    } else if (value > 100) {
      warnings.push({ scene_ordinal: point.scene_ordinal, value, kind: "above_100" });
    }
  }
  return warnings;
}

export type YScale = {
  mode: YDomainMode;
  domainMin: number;
  domainMax: number;
  ticks: number[];
  yForValue: (value: number) => number;
  /** Map raw value for display without silent clip of domain; still draws within pad. */
  plotY: (value: number | null) => number | null;
};

export function computeYScale(
  series: JourneyCurvePoint[],
  chartHeight: number,
  mode: YDomainMode = DEFAULT_Y_DOMAIN_MODE,
): YScale {
  const padTop = CHART_PAD.top;
  const padBottom = CHART_PAD.bottom;
  const plotHeight = Math.max(chartHeight - padTop - padBottom, 1);

  let domainMin = 0;
  let domainMax = 100;
  let ticks: number[] = [...Y_TICKS_FIXED];

  if (mode === "focus_data") {
    const values = series
      .map((p) => resolveMetricValue(p))
      .filter((v): v is number => v != null);
    if (values.length > 0) {
      const min = Math.min(...values);
      const max = Math.max(...values);
      const pad = Math.max((max - min) * 0.08, 4);
      domainMin = Math.max(0, Math.floor((min - pad) / 5) * 5);
      domainMax = Math.min(100, Math.ceil((max + pad) / 5) * 5);
      if (domainMax <= domainMin) {
        domainMin = Math.max(0, domainMin - 5);
        domainMax = Math.min(100, domainMax + 5);
      }
      const step = Math.max((domainMax - domainMin) / 4, 1);
      ticks = Array.from({ length: 5 }, (_, i) =>
        Math.round(domainMin + step * i),
      );
      ticks[ticks.length - 1] = domainMax;
    }
  }

  const span = Math.max(domainMax - domainMin, 1e-6);

  const yForValue = (value: number) => {
    const t = (value - domainMin) / span;
    return padTop + plotHeight - t * plotHeight;
  };

  const plotY = (value: number | null) => {
    if (value == null || !Number.isFinite(value)) return null;
    return yForValue(value);
  };

  return { mode, domainMin, domainMax, ticks, yForValue, plotY };
}

export function xForSceneOrdinal(
  ordinal: number,
  sceneCount: number,
  chartWidth: number,
): number {
  const plotWidth = chartWidth - CHART_PAD.left - CHART_PAD.right;
  if (sceneCount <= 1) return CHART_PAD.left + plotWidth / 2;
  return CHART_PAD.left + ((ordinal - 1) / (sceneCount - 1)) * plotWidth;
}

/** Build SVG path(s) with breaks on null; does not coerce missing to 0. */
export function buildLinePathD(
  series: JourneyCurvePoint[],
  xFor: (ordinal: number) => number,
  yFor: (value: number) => number,
): string {
  const segments: string[] = [];
  let current: string[] = [];

  const flush = () => {
    if (current.length === 0) return;
    segments.push(current.join(" "));
    current = [];
  };

  for (const point of series) {
    const value = resolveMetricValue(point);
    if (value == null) {
      flush();
      continue;
    }
    const x = xFor(point.scene_ordinal);
    const y = yFor(value);
    if (current.length === 0) {
      current.push(`M ${x} ${y}`);
    } else {
      current.push(`L ${x} ${y}`);
    }
  }
  flush();
  return segments.join(" ");
}

export function clampViewWindow(
  start: number,
  end: number,
  sceneCount: number,
  minSpan: number,
): { start: number; end: number } {
  if (sceneCount <= 0) return { start: 1, end: 1 };
  let s = Math.max(1, Math.min(start, sceneCount));
  let e = Math.max(1, Math.min(end, sceneCount));
  if (e < s) [s, e] = [e, s];
  const span = e - s + 1;
  if (span < minSpan) {
    e = Math.min(sceneCount, s + minSpan - 1);
    s = Math.max(1, e - minSpan + 1);
  }
  return { start: s, end: e };
}

export function focusPhaseWindow(
  phaseStart: number,
  phaseEnd: number,
  sceneCount: number,
  padding = 1,
): { start: number; end: number } {
  return clampViewWindow(phaseStart - padding, phaseEnd + padding, sceneCount, 1);
}

export function zoomViewWindow(
  start: number,
  end: number,
  sceneCount: number,
  factor: number,
  anchorOrdinal?: number | null,
): { start: number; end: number } {
  const span = end - start + 1;
  const nextSpan = Math.max(2, Math.round(span / factor));
  const anchor =
    anchorOrdinal != null && anchorOrdinal >= start && anchorOrdinal <= end
      ? anchorOrdinal
      : Math.round((start + end) / 2);
  const half = Math.floor(nextSpan / 2);
  return clampViewWindow(anchor - half, anchor - half + nextSpan - 1, sceneCount, 2);
}
