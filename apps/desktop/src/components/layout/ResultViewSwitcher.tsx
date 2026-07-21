type View = "analysis" | "journey";

type Props = {
  active: View;
  onChange: (view: View) => void;
  journeyAvailable?: boolean;
  analysisLabel?: string;
  journeyLabel?: string;
};

export function ResultViewSwitcher({
  active,
  onChange,
  journeyAvailable = true,
  analysisLabel = "场景分析",
  journeyLabel = "阅读旅程",
}: Props) {
  return (
    <div className="result-view-switcher" data-testid="result-view-switcher" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={active === "analysis"}
        className={active === "analysis" ? "active" : ""}
        data-testid="result-view-analysis"
        onClick={() => onChange("analysis")}
      >
        {analysisLabel}
      </button>
      <button
        type="button"
        role="tab"
        aria-selected={active === "journey"}
        className={active === "journey" ? "active" : ""}
        data-testid="result-view-journey"
        disabled={!journeyAvailable}
        onClick={() => onChange("journey")}
      >
        {journeyLabel}
      </button>
    </div>
  );
}
