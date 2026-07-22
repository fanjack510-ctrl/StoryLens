import type { JourneyPageMode } from "../../types/journeySelection";
import { pageModeToJourneyView, type JourneyViewMode } from "./journeyViewMode";

type Props = {
  pageMode: JourneyPageMode;
  onChange: (mode: JourneyPageMode) => void;
};

const OPTIONS: { mode: JourneyPageMode; view: JourneyViewMode; label: string; testId: string }[] = [
  { mode: "sync", view: "compare", label: "正文对照", testId: "journey-mode-sync" },
  { mode: "journey", view: "journey", label: "旅程视图", testId: "journey-mode-journey" },
  { mode: "reading", view: "text", label: "仅看正文", testId: "journey-mode-reading" },
];

/**
 * Secondary Journey mode switcher (compare / journey / text-only).
 * Labels must never collide with primary WorkspaceTab「正文阅读」.
 */
export function JourneyModeSwitcher({ pageMode, onChange }: Props) {
  return (
    <div
      className="journey-sync-mode-toggle"
      data-testid="journey-sync-mode-toggle"
      data-journey-view={pageModeToJourneyView(pageMode)}
      role="tablist"
      aria-label="阅读旅程内部视图"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.mode}
          type="button"
          role="tab"
          data-testid={opt.testId}
          data-journey-view={opt.view}
          className={pageMode === opt.mode ? "active" : ""}
          onClick={() => onChange(opt.mode)}
          aria-pressed={pageMode === opt.mode}
          aria-selected={pageMode === opt.mode}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
