import { useId, useState } from "react";
import type { ObservationLensId } from "./observationLenses";
import {
  OVERLAY_COMPARE_HOW_TO_READ,
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

/** Layer 1 one-liner + Layer 2 "怎么看" (max 3) + metric/node legends. */
export function JourneyLensExplanationChrome({
  lensId,
  overlayCompare = false,
  comparisonActive = false,
  primaryMetricLabel = null,
  compareMetricLabel = null,
  hookPayoffStats = null,
  inconsistentWarning = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const explanation = getLensExplanation(lensId);
  const title = explanation.chart_title || explanation.title;
  const summary = overlayCompare && comparisonActive
    ? OVERLAY_COMPARE_SUMMARY
    : explanation.one_line_summary;
  const howTo =
    overlayCompare && comparisonActive ? OVERLAY_COMPARE_HOW_TO_READ : explanation.how_to_read;
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
      <div className="journey-lens-explanation-row">
        <p className="journey-lens-one-liner" data-testid="journey-lens-one-liner">
          <strong data-testid="journey-lens-title">{title}</strong>
          {" · "}
          {summary}
        </p>
        <button
          type="button"
          className="journey-lens-how-to-trigger"
          data-testid="journey-lens-how-to-trigger"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
        >
          怎么看
        </button>
      </div>
      {open ? (
        <ol
          id={panelId}
          className="journey-lens-how-to-panel"
          data-testid="journey-lens-how-to-panel"
        >
          {howTo.slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ol>
      ) : null}
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
      <ul className="journey-minimal-legend" data-testid="journey-minimal-legend">
        {explanation.legend_items.map((item) => (
          <li key={item.key} data-legend={item.key}>
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
