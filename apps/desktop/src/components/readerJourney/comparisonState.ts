/**
 * Explicit Reader Journey comparison mode state.
 * Active only when a valid compare metric differs from the primary lens metric.
 */

import { getObservationLens, type ObservationLensId } from "./observationLenses";

export type CompareMetricKey =
  | "reading_momentum"
  | "plot_progress"
  | "reading_tension"
  | "arousal"
  | "pacing_speed"
  | "engagement";

export const COMPARE_CANDIDATE_METRICS: {
  key: Exclude<CompareMetricKey, "engagement">;
  label: string;
}[] = [
  { key: "reading_momentum", label: "综合阅读动力" },
  { key: "plot_progress", label: "剧情推进" },
  { key: "reading_tension", label: "阅读张力" },
  { key: "arousal", label: "情绪强度" },
  { key: "pacing_speed", label: "节奏速度" },
];

export type ComparisonState =
  | {
      mode: "inactive";
      primaryMetric: string;
      primaryLabel: string;
      compareMetric: null;
      compareLabel: null;
    }
  | {
      mode: "active";
      primaryMetric: string;
      primaryLabel: string;
      compareMetric: CompareMetricKey;
      compareLabel: string;
    };

const COMPARE_METRIC_SET = new Set<string>([
  ...COMPARE_CANDIDATE_METRICS.map((m) => m.key),
  "engagement",
]);

export function labelForCompareMetric(metric: string): string {
  if (metric === "engagement") return "综合阅读动力";
  return COMPARE_CANDIDATE_METRICS.find((m) => m.key === metric)?.label ?? metric;
}

export function isValidCompareMetric(value: string | null | undefined): value is CompareMetricKey {
  return Boolean(value && COMPARE_METRIC_SET.has(value));
}

/** Normalize URL / raw compare value; invalid or same-as-primary → null. */
export function sanitizeCompareMetric(
  raw: string | null | undefined,
  primaryMetric: string,
): CompareMetricKey | null {
  if (!isValidCompareMetric(raw)) return null;
  const normalized = raw === "engagement" ? "reading_momentum" : raw;
  if (normalized === primaryMetric || raw === primaryMetric) return null;
  return raw;
}

/**
 * Build comparison state from lens + compareWith.
 * Equality uses lens.primaryKey (reading_momentum / arousal / …).
 */
export function buildComparisonState(
  lensId: ObservationLensId,
  compareWith: string | null | undefined,
): ComparisonState {
  const lens = getObservationLens(lensId);
  const primaryKey = lens.primaryKey;
  const primaryLabel = lens.labelZh;
  if (lens.isPairedHookPayoff) {
    return {
      mode: "inactive",
      primaryMetric: primaryKey,
      primaryLabel,
      compareMetric: null,
      compareLabel: null,
    };
  }
  const cleaned = sanitizeCompareMetric(compareWith == null ? null : String(compareWith), primaryKey);
  if (!cleaned) {
    return {
      mode: "inactive",
      primaryMetric: primaryKey,
      primaryLabel,
      compareMetric: null,
      compareLabel: null,
    };
  }
  return {
    mode: "active",
    primaryMetric: primaryKey,
    primaryLabel,
    compareMetric: cleaned,
    compareLabel: labelForCompareMetric(cleaned),
  };
}

/** When switching lens: keep compare unless same-as-primary or hook_payoff. */
export function resolveCompareAfterLensChange(
  nextLens: ObservationLensId,
  previousCompare: string | null,
): { compare: CompareMetricKey | null; exitedSameMetric: boolean } {
  if (nextLens === "hook_payoff") {
    return { compare: null, exitedSameMetric: false };
  }
  const primaryKey = getObservationLens(nextLens).primaryKey;
  if (
    previousCompare &&
    (previousCompare === primaryKey ||
      (previousCompare === "engagement" && primaryKey === "reading_momentum") ||
      (previousCompare === "reading_momentum" && primaryKey === "reading_momentum"))
  ) {
    return { compare: null, exitedSameMetric: true };
  }
  const cleaned = sanitizeCompareMetric(previousCompare, primaryKey);
  return { compare: cleaned, exitedSameMetric: false };
}
