type WorkspaceTab = "reading" | "analysis" | "journey";

type Props = {
  active: WorkspaceTab;
  onChange: (tab: WorkspaceTab) => void;
  /** Scene results exist (or scenes finished) — analysis tab enabled. */
  analysisAvailable?: boolean;
  /** Journey visualization ready — journey tab opens frozen result. */
  journeyAvailable?: boolean;
  /** Journey still generating — journey tab stays clickable for progress. */
  journeyInProgress?: boolean;
};

/**
 * Book workspace top tabs: 正文阅读 | 场景分析 | 阅读旅程.
 * Stays inside BookRoutePage; does not change app shell.
 */
export function WorkspaceViewSwitcher({
  active,
  onChange,
  analysisAvailable = true,
  journeyAvailable = false,
  journeyInProgress = false,
}: Props) {
  const journeyEnabled = journeyAvailable || journeyInProgress;
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
      <button
        type="button"
        role="tab"
        aria-selected={active === "analysis"}
        className={active === "analysis" ? "active" : ""}
        data-testid="workspace-tab-analysis"
        disabled={!analysisAvailable}
        onClick={() => onChange("analysis")}
      >
        场景分析
      </button>
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
    </div>
  );
}
