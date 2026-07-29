type WorkspaceTab = "reading" | "analysis" | "journey";

type Props = {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  /** @deprecated CHG-011: analysis tab removed from ordinary nav. */
  analysisAvailable?: boolean;
  /** Journey visualization ready — journey tab opens frozen result. */
  journeyAvailable?: boolean;
  /** Journey still generating — journey tab stays clickable for progress. */
  journeyInProgress?: boolean;
  /** CHG-011: hide journey before scene confirmation. */
  showJourneyTab?: boolean;
  /** CHG-011: never show analysis tab in ordinary nav when false. */
  showAnalysisTab?: boolean;
};

/**
 * Book workspace top tabs: 正文阅读 | 阅读旅程.
 * 「场景分析」已从普通主导航移除（CHG-011）。
 */
export function WorkspaceViewSwitcher({
  active,
  onChange,
  journeyAvailable = false,
  journeyInProgress = false,
  showJourneyTab = true,
  showAnalysisTab = false,
}: Props) {
  const journeyEnabled = showJourneyTab && (journeyAvailable || journeyInProgress);
  return (
    <div className="result-view-switcher" data-testid="workspace-view-switcher" role="tablist">
      <button
        type="button"
        role="tab"
        aria-selected={active === "reading"}
        className={active === "reading" ? "active" : ""}
        data-testid="workspace-tab-reading"
        onClick={() => onChange("reading")}
      >
        正文阅读
      </button>
      {showAnalysisTab ? (
        <button
          type="button"
          role="tab"
          aria-selected={active === "analysis"}
          className={active === "analysis" ? "active" : ""}
          data-testid="workspace-tab-analysis"
          onClick={() => onChange("analysis")}
        >
          场景分析
        </button>
      ) : null}
      {showJourneyTab ? (
        <button
          type="button"
          role="tab"
          aria-selected={active === "journey"}
          className={active === "journey" ? "active" : ""}
          data-testid="workspace-tab-journey"
          disabled={!journeyEnabled}
          onClick={() => onChange("journey")}
        >
          阅读旅程
        </button>
      ) : null}
    </div>
  );
}
