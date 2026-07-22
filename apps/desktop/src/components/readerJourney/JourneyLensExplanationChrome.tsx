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
  overlayCompare?: boolean;
  hookPayoffStats?: HookPayoffChapterStats | null;
  inconsistentWarning?: string | null;
};

/** Layer 1 one-liner + Layer 2 "怎么看" (max 3) + optional hook/payoff stats. */
export function JourneyLensExplanationChrome({
  lensId,
  overlayCompare = false,
  hookPayoffStats = null,
  inconsistentWarning = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const explanation = getLensExplanation(lensId);
  const summary = overlayCompare ? OVERLAY_COMPARE_SUMMARY : explanation.one_line_summary;
  const howTo = overlayCompare ? OVERLAY_COMPARE_HOW_TO_READ : explanation.how_to_read;
  const legend = explanation.legend_items;

  return (
    <div className="journey-lens-explanation" data-testid="journey-lens-explanation" data-lens={lensId}>
      {inconsistentWarning ? (
        <p className="journey-loop-inconsistent-banner" data-testid="journey-loop-inconsistent-banner">
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
      <ul className="journey-minimal-legend" data-testid="journey-minimal-legend">
        {legend.map((item) => (
          <li key={item.key} data-legend={item.key}>
            {item.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
