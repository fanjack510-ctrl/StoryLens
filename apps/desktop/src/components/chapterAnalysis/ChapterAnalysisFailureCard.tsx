import { useState } from "react";
import type { Run } from "../../types";
import { userFacingFailureHint } from "./mapAnalysisUiState";

type Props = {
  run: Run;
  canResume: boolean;
  resumeBusy?: boolean;
  onResume?: () => void;
  onReanalyze?: () => void;
  completed?: number;
  total?: number;
  remaining?: number;
  costLabel?: string | null;
};

export function ChapterAnalysisFailureCard({
  run,
  canResume,
  resumeBusy,
  onResume,
  onReanalyze,
  completed = 0,
  total = 0,
  remaining,
  costLabel,
}: Props) {
  const [techOpen, setTechOpen] = useState(false);
  const left =
    typeof remaining === "number"
      ? remaining
      : total > 0
        ? Math.max(0, total - completed)
        : undefined;

  return (
    <div className="chapter-analysis-failure-card" data-testid="chapter-analysis-failure">
      <h3>分析未完成</h3>
      <p data-testid="chapter-analysis-failure-hint">{userFacingFailureHint(run)}</p>
      <ul className="chapter-analysis-failure-stats">
        {total > 0 && (
          <li data-testid="chapter-analysis-failure-progress">
            已完成 {completed} / {total}
            {typeof left === "number" ? ` · 剩余 ${left}` : ""}
          </li>
        )}
        {costLabel && <li data-testid="chapter-analysis-failure-cost">{costLabel}</li>}
        {canResume && <li>可以尝试恢复同一任务</li>}
      </ul>
      <div className="chapter-analysis-failure-actions">
        {canResume && onResume && (
          <button
            type="button"
            className="primary"
            data-testid="chapter-analysis-resume"
            disabled={resumeBusy}
            onClick={onResume}
          >
            {resumeBusy ? "正在恢复…" : "恢复分析"}
          </button>
        )}
        {onReanalyze && (
          <button
            type="button"
            className="secondary"
            data-testid="chapter-analysis-reanalyze"
            onClick={onReanalyze}
          >
            重新分析
          </button>
        )}
        <button
          type="button"
          className="ghost"
          data-testid="chapter-analysis-tech-toggle"
          onClick={() => setTechOpen((v) => !v)}
        >
          {techOpen ? "收起技术详情" : "查看技术详情"}
        </button>
      </div>
      {techOpen && (
        <pre className="chapter-analysis-tech" data-testid="chapter-analysis-tech-details">
          {JSON.stringify(
            {
              status: run.status,
              error_code: run.error_code,
              root_error_code: run.root_error_code,
              failed_stage: run.failed_stage,
              retryable: run.retryable,
            },
            null,
            2,
          )}
        </pre>
      )}
    </div>
  );
}
