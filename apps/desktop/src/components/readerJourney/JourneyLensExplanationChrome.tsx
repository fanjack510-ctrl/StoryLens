import type { ObservationLensId } from "./observationLenses";
import {
  OVERLAY_COMPARE_SUMMARY,
  getLensExplanation,
} from "./readerJourneyLensExplanation";
import type { HookPayoffChapterStats } from "./hookPayoffTimelineModel";

type Props = {
  lensId: ObservationLensId;
  /** @deprecated Kept for call-site compat; title no longer switches to overlay label. */
  overlayCompare?: boolean;
  comparisonActive?: boolean;
  primaryMetricLabel?: string | null;
  compareMetricLabel?: string | null;
  hookPayoffStats?: HookPayoffChapterStats | null;
  inconsistentWarning?: string | null;
};

/** Compact lens title + one-liner + single legend set (no duplicate 怎么看 panel). */
export function JourneyLensExplanationChrome({
  lensId,
  overlayCompare = false,
  comparisonActive = false,
  primaryMetricLabel = null,
  compareMetricLabel = null,
  hookPayoffStats = null,
  inconsistentWarning = null,
}: Props) {
  const explanation = getLensExplanation(lensId);
  const title = explanation.chart_title || explanation.title;
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
      <p className="journey-lens-one-liner" data-testid="journey-lens-one-liner">
        <strong data-testid="journey-lens-title">{title}</strong>
        {" · "}
        {summary}
      </p>
      <div className="journey-unified-legend" data-testid="journey-unified-legend">
        {lensId !== "hook_payoff" ? (
          <ul
            className="journey-metric-legend"
            data-testid="journey-metric-legend"
            aria-label="指标图例"
          >
            <li data-legend="primary">绿色实线：{primaryLabel}</li>
            {showCompareLegend ? (
              <li data-legend="compare">紫色虚线：{compareMetricLabel}</li>
            ) : null}
          </ul>
        ) : null}
        <ul
          className="journey-minimal-legend"
          data-testid="journey-minimal-legend"
          aria-label="节点图例"
        >
          {explanation.legend_items.map((item) => (
            <li key={item.key} data-legend={item.key}>
              {item.label}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
