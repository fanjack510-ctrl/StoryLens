type Props = {
  /** True when succeeded journey visualization exists for the current chapter run. */
  hasJourney: boolean;
  /** Open Start Analysis (chapter pipeline that produces reader journey). */
  onAnalyze: () => void;
  /** Open existing journey result (workspace tab or deep link). */
  onView: () => void;
  disabled?: boolean;
};

/**
 * Free single-chapter reader journey entry (CHG-20260726-007).
 * Distinct from Native Overview and Chapter Aggregation Insights.
 * Labels align with Free 1.0.5 result chrome ("查看读者旅程") plus
 * discoverable analyze entry when no journey result exists.
 */
export function ReaderJourneyEntry({
  hasJourney,
  onAnalyze,
  onView,
  disabled = false,
}: Props) {
  if (hasJourney) {
    return (
      <button
        type="button"
        className="secondary reader-journey-entry"
        data-testid="reader-journey-entry-view"
        disabled={disabled}
        onClick={onView}
      >
        查看读者旅程
      </button>
    );
  }

  return (
    <button
      type="button"
      className="secondary reader-journey-entry"
      data-testid="reader-journey-entry-analyze"
      disabled={disabled}
      onClick={onAnalyze}
    >
      分析读者旅程
    </button>
  );
}
