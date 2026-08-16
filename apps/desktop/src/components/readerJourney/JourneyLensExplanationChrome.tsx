import type { ObservationLensId } from "./observationLenses";
import {
  OVERLAY_COMPARE_SUMMARY,
  getLensExplanation,
} from "./readerJourneyLensExplanation";
import type { HookPayoffChapterStats } from "./hookPayoffTimelineModel";
import type { HookVocabulary } from "../../types/readerJourneyVisualization";

/**
 * The legend's four keys are the four structural hook actions, so they translate the same
 * way the trajectory labels do. Any other legend row (场景 / 节拍 / 悬念欠账 …) passes through.
 */
function legendLabelZh(
  item: { key: string; label: string },
  vocabulary: HookVocabulary | null | undefined,
): string {
  if (!vocabulary) return item.label;
  switch (item.key) {
    case "raise":
      return vocabulary.open || item.label;
    case "deepen":
      return vocabulary.deepen || item.label;
    case "answer":
      return vocabulary.answer || item.label;
    case "carry":
      return vocabulary.carry || item.label;
    default:
      return item.label;
  }
}

type Props = {
  lensId: ObservationLensId;
  /** @deprecated Kept for call-site compat; title no longer switches to overlay label. */
  overlayCompare?: boolean;
  comparisonActive?: boolean;
  primaryMetricLabel?: string | null;
  compareMetricLabel?: string | null;
  hookPayoffStats?: HookPayoffChapterStats | null;
  inconsistentWarning?: string | null;
  /** When false, omit node/metric legends (rendered above the chart instead). */
  showLegend?: boolean;
  /**
   * The main curve's name for this book. Renaming only the toolbar button left twelve
   * places on the page still saying 综合阅读 under a button reading 追读意愿 — the reader
   * has no way to know they are the same thing.
   */
  mainCurveLabel?: string | null;
  /**
   * Backend-owned wording for the four hook actions, forwarded to the legend below the
   * toolbar. Without it the legend prints the suspense set directly above a trajectory
   * labelled in the book's own terms — 「提出疑问」 over 「起了心结」, two vocabularies on one
   * screen.
   */
  hookVocabulary?: HookVocabulary | null;
  /** When true the definition line is suppressed; it lives on the button's tooltip. */
  hideOneLiner?: boolean;
};

/** Compact lens title + one-liner from unified explanation config. */
export function JourneyLensExplanationChrome({
  lensId,
  overlayCompare = false,
  comparisonActive = false,
  primaryMetricLabel = null,
  compareMetricLabel = null,
  hookPayoffStats = null,
  inconsistentWarning = null,
  showLegend = false,
  mainCurveLabel = null,
  hookVocabulary = null,
  hideOneLiner = false,
}: Props) {
  const explanation = getLensExplanation(lensId);
  // Both named lenses wear the book's own name; the rest keep theirs.
  const title =
    lensId === "composite" && mainCurveLabel
      ? mainCurveLabel
      : lensId === "hook_payoff" && hookVocabulary?.lens
        ? hookVocabulary.lens
        : explanation.title;
  const summary =
    overlayCompare && comparisonActive
      ? OVERLAY_COMPARE_SUMMARY
      : explanation.one_line_summary;
  const primaryLabel = primaryMetricLabel || explanation.title;
  const showCompareLegend = Boolean(comparisonActive && compareMetricLabel);

  return (
    <div className="journey-lens-explanation" data-testid="journey-lens-explanation" data-lens={lensId}>
      {inconsistentWarning ? (
        <p
          className={
            inconsistentWarning.includes("严重冲突")
              ? "journey-loop-inconsistent-banner"
              : "journey-loop-soft-conflict-banner"
          }
          data-testid={
            inconsistentWarning.includes("严重冲突")
              ? "journey-loop-inconsistent-banner"
              : "journey-loop-soft-conflict-banner"
          }
        >
          {inconsistentWarning}
        </p>
      ) : null}
      {lensId === "hook_payoff" && hookPayoffStats ? (
        <ul className="journey-hook-payoff-stats" data-testid="journey-hook-payoff-stats">
          <li>本章建立问题：{hookPayoffStats.established}</li>
          <li>已经回应：{hookPayoffStats.answered}</li>
          <li>仍在等待：{hookPayoffStats.waiting}</li>
          <li>存在拖延风险：{hookPayoffStats.delayed_risk}</li>
        </ul>
      ) : null}
      {hideOneLiner ? (
        // The definition is useful once and then costs two rows on every lens switch; it is
        // carried by the main button's tooltip instead. The title stays for screen readers
        // and for the tests that identify the active lens by it.
        <p className="journey-lens-one-liner is-compact" data-testid="journey-lens-one-liner">
          <strong data-testid="journey-lens-title">{title}</strong>
        </p>
      ) : (
        <p className="journey-lens-one-liner" data-testid="journey-lens-one-liner">
          <strong data-testid="journey-lens-title">{title}</strong>
          {"："}
          {summary.replace(new RegExp(`^${explanation.title}：`), "")}
        </p>
      )}
      {showLegend ? (
        <JourneyChartLegend
          lensId={lensId}
          primaryMetricLabel={primaryLabel}
          compareMetricLabel={showCompareLegend ? compareMetricLabel : null}
          hookVocabulary={hookVocabulary}
        />
      ) : null}
    </div>
  );
}

/** Single centered legend placed directly above the journey curve. */
export function JourneyChartLegend({
  lensId,
  primaryMetricLabel = null,
  compareMetricLabel = null,
  hookVocabulary = null,
}: {
  lensId: ObservationLensId;
  primaryMetricLabel?: string | null;
  compareMetricLabel?: string | null;
  hookVocabulary?: HookVocabulary | null;
}) {
  const explanation = getLensExplanation(lensId);
  const primaryLabel = primaryMetricLabel || explanation.title;
  const showMetricLines = Boolean(compareMetricLabel) && lensId !== "hook_payoff";
  return (
    <div
      className="journey-unified-legend journey-chart-legend-above"
      data-testid="journey-unified-legend"
      data-legend-placement="above-chart"
    >
      {showMetricLines ? (
        <ul
          className="journey-metric-legend"
          data-testid="journey-metric-legend"
          aria-label="指标图例"
        >
          <li data-legend="primary">绿色实线：{primaryLabel}</li>
          <li data-legend="compare">紫色虚线：{compareMetricLabel}</li>
        </ul>
      ) : null}
      <ul
        className="journey-minimal-legend"
        data-testid="journey-minimal-legend"
        aria-label="节点图例"
      >
        {explanation.legend_items.map((item) => (
          <li key={item.key} data-legend={item.key}>
            {legendLabelZh(item, hookVocabulary)}
          </li>
        ))}
      </ul>
    </div>
  );
}
