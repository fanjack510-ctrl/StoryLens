import { uiStateLabel, type ChapterAnalysisUiState } from "./mapAnalysisUiState";

type Props = {
  state: ChapterAnalysisUiState;
  className?: string;
};

export function ChapterAnalysisStatusBadge({ state, className = "" }: Props) {
  return (
    <span
      className={`chapter-analysis-status-badge state-${state} ${className}`.trim()}
      data-testid="chapter-analysis-status-badge"
      data-ui-state={state}
    >
      {uiStateLabel(state)}
    </span>
  );
}
