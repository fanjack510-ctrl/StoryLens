import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import type { Run } from "../../types";
import {
  shouldShowUnifiedRecovery,
  UnifiedAnalysisRecoveryCard,
} from "./UnifiedAnalysisRecoveryCard";
import { ChapterAnalysisFailureCard } from "./ChapterAnalysisFailureCard";
import { ChapterAnalysisStatusBadge } from "./ChapterAnalysisStatusBadge";
import {
  budgetSummary,
  elapsedLabel,
  progressCounts,
  readerJourneyStageLabel,
  stageLabelForRun,
  stageSteps,
  uiStateLabel,
  type ChapterAnalysisUiState,
} from "./mapAnalysisUiState";
import "./chapterAnalysis.css";

type UsageSnapshot = {
  request_count?: number;
  total_tokens?: number;
  estimated_cost?: number;
  remaining_requests?: number;
  remaining_tokens?: number;
  remaining_estimated_cost?: number;
};

type Props = {
  run: Run | null;
  uiState: ChapterAnalysisUiState;
  chapterTitle?: string;
  reconnectHint?: boolean;
  canResume?: boolean;
  onResume?: () => Promise<void> | void;
  onReanalyze?: () => void;
  onReviewBoundary?: () => void;
  onDismiss?: () => void;
  onContinueReading?: () => void;
  /** Stay on /books and open embedded results (Phase 1C-C.2.3C). */
  onViewResults?: () => void;
  /** Open journey resume / workspace entry on the chapter shell. */
  onContinueReaderJourney?: () => void;
  onBudgetContinued?: () => void;
};

export function ChapterAnalysisProgressPanel({
  run,
  uiState,
  chapterTitle,
  reconnectHint,
  canResume,
  onResume,
  onReanalyze,
  onReviewBoundary,
  onDismiss,
  onContinueReading,
  onViewResults,
  onContinueReaderJourney,
  onBudgetContinued,
}: Props) {
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumeError, setResumeError] = useState<string>();
  const [hasJourney, setHasJourney] = useState(false);
  const counts = progressCounts(run);
  const pct =
    counts.total > 0 ? Math.min(100, Math.round((counts.current / counts.total) * 100)) : 0;
  const steps = stageSteps(uiState, run);
  const cost = run ? budgetSummary(run) : null;
  const elapsed = run ? elapsedLabel(run) : null;
  const usageQuery = useQuery({
    queryKey: ["cloud-usage"],
    queryFn: settingsApi.cloudUsage,
    enabled: Boolean(run),
    refetchInterval: uiState === "running" ? 8000 : 20000,
  });
  const usage = usageQuery.data as UsageSnapshot | undefined;

  useEffect(() => {
    let cancelled = false;
    if (uiState !== "succeeded" || !run) {
      setHasJourney(false);
      return;
    }
    void analysisApi
      .readerJourney(run.id)
      .then((data) => {
        if (!cancelled) {
          setHasJourney(Boolean(data?.status === "succeeded" && data.visualization));
        }
      })
      .catch(() => {
        if (!cancelled) setHasJourney(false);
      });
    return () => {
      cancelled = true;
    };
  }, [uiState, run]);

  const handleResume = async () => {
    if (!onResume || resumeBusy) return;
    setResumeBusy(true);
    setResumeError(undefined);
    try {
      await onResume();
    } catch (error) {
      setResumeError((error as Error).message || "恢复失败");
    } finally {
      setResumeBusy(false);
    }
  };

  const showMeter =
    run &&
    (uiState === "running" ||
      uiState === "partial" ||
      uiState === "boundary_review_required" ||
      uiState === "awaiting_budget_adjustment" ||
      uiState === "aborted_by_limit" ||
      uiState === "provider_recovery");

  return (
    <aside
      className="chapter-analysis-progress-panel"
      data-testid="chapter-analysis-progress"
      data-ui-state={uiState}
    >
      <header className="chapter-analysis-progress-head">
        <div>
          <small>章节分析</small>
          <h2>章节分析</h2>
          {chapterTitle && (
            <p className="chapter-analysis-chapter" data-testid="chapter-analysis-chapter">
              {chapterTitle}
            </p>
          )}
        </div>
        {onDismiss && (
          <button type="button" className="ghost" data-testid="chapter-analysis-dismiss" onClick={onDismiss}>
            收起
          </button>
        )}
      </header>

      <ChapterAnalysisStatusBadge state={uiState} />

      {run && (
        <dl className="chapter-analysis-run-meta" data-testid="chapter-analysis-run-meta">
          <div>
            <dt>Run ID</dt>
            <dd data-testid="chapter-analysis-run-id">#{run.id}</dd>
          </div>
          <div>
            <dt>当前阶段</dt>
            <dd data-testid="chapter-analysis-stage">{stageLabelForRun(run)}</dd>
          </div>
          <div>
            <dt>Scene 进度</dt>
            <dd data-testid="chapter-analysis-scene-progress">
              {counts.total > 0 ? `${counts.current} / ${counts.total}` : "—"}
            </dd>
          </div>
          <div>
            <dt>当前 Scene</dt>
            <dd data-testid="chapter-analysis-current-scene">
              {typeof run.failed_scene_index === "number"
                ? `#${run.failed_scene_index}`
                : counts.total > 0
                  ? counts.current < counts.total
                    ? `#${counts.current + 1}`
                    : "已完成"
                  : "—"}
            </dd>
          </div>
          <div>
            <dt>Reader Journey</dt>
            <dd data-testid="chapter-analysis-journey-stage">
              {readerJourneyStageLabel(run, uiState)}
            </dd>
          </div>
          <div>
            <dt>状态</dt>
            <dd data-testid="chapter-analysis-status-text">{uiStateLabel(uiState)}</dd>
          </div>
          <div>
            <dt>今日请求</dt>
            <dd data-testid="chapter-analysis-today-requests">
              {typeof usage?.request_count === "number"
                ? `${usage.request_count}`
                : typeof run.budget_remaining?.requests === "number"
                  ? `剩余 ${run.budget_remaining.requests}`
                  : "—"}
              {typeof usage?.remaining_requests === "number"
                ? ` · 剩余 ${usage.remaining_requests}`
                : ""}
            </dd>
          </div>
          <div>
            <dt>Token</dt>
            <dd data-testid="chapter-analysis-today-tokens">
              {typeof usage?.total_tokens === "number"
                ? `${usage.total_tokens}`
                : typeof run.budget_remaining?.tokens === "number"
                  ? `剩余 ${run.budget_remaining.tokens}`
                  : "—"}
            </dd>
          </div>
          <div>
            <dt>费用</dt>
            <dd data-testid="chapter-analysis-today-cost">
              {typeof usage?.estimated_cost === "number"
                ? `${usage.estimated_cost} CNY`
                : typeof run.budget_remaining?.estimated_cost === "number"
                  ? `剩余 ${run.budget_remaining.estimated_cost} CNY`
                  : "—"}
            </dd>
          </div>
        </dl>
      )}

      <ol className="chapter-analysis-stages" data-testid="chapter-analysis-stages">
        {steps.map((step) => (
          <li key={step.id} data-tone={step.tone} data-testid={`chapter-analysis-stage-${step.id}`}>
            <span className="stage-mark" aria-hidden>
              {step.tone === "done" ? "✓" : step.tone === "active" ? "●" : "○"}
            </span>
            {step.label}
          </li>
        ))}
      </ol>

      {reconnectHint && (
        <p className="notice" data-testid="chapter-analysis-reconnect">
          正在重新连接…
        </p>
      )}

      {showMeter && (
        <div className="chapter-analysis-meter" data-testid="chapter-analysis-meter">
          <div className="chapter-analysis-meter-bar">
            <span style={{ width: `${pct}%` }} />
          </div>
          <p data-testid="chapter-analysis-count">
            {counts.total > 0 ? `${counts.current} / ${counts.total}` : uiStateLabel(uiState)}
          </p>
          {elapsed && <p data-testid="chapter-analysis-elapsed">已用时间 {elapsed}</p>}
          {cost && <p data-testid="chapter-analysis-budget">{cost}</p>}
        </div>
      )}

      {uiState === "boundary_review_required" && (
        <div className="chapter-analysis-boundary" data-testid="chapter-analysis-boundary">
          <p>需要确认场景边界后才能继续场景分析。</p>
          <button
            type="button"
            className="primary"
            data-testid="chapter-analysis-review-boundary"
            onClick={onReviewBoundary}
          >
            审阅场景边界
          </button>
        </div>
      )}

      {run && shouldShowUnifiedRecovery(uiState) && (
        <UnifiedAnalysisRecoveryCard
          run={run}
          variant="card"
          onContinued={onBudgetContinued}
          onLater={onDismiss}
        />
      )}

      {(uiState === "failed" || uiState === "partial") &&
        run &&
        !shouldShowUnifiedRecovery(uiState) && (
        <ChapterAnalysisFailureCard
          run={run}
          canResume={Boolean(canResume)}
          resumeBusy={resumeBusy}
          onResume={handleResume}
          onReanalyze={onReanalyze}
          completed={counts.current}
          total={counts.total}
          remaining={run.remaining_scene_count}
          costLabel={cost}
        />
      )}
      {resumeError && (
        <p className="notice error" data-testid="chapter-analysis-resume-error">
          {resumeError}
        </p>
      )}

      {uiState === "reader_journey_processing" && run && (
        <div
          className="chapter-analysis-success"
          data-testid="chapter-analysis-journey-processing"
        >
          <h3>正在生成阅读旅程</h3>
          <p>AnalysisRun #{run.id} 保持不变；任务中心可同步查看进度。</p>
          {onViewResults && (
            <button
              type="button"
              className="secondary"
              data-testid="chapter-analysis-open-results"
              onClick={onViewResults}
            >
              查看章节页进度
            </button>
          )}
        </div>
      )}

      {uiState === "succeeded" && run && (
        <div className="chapter-analysis-success" data-testid="chapter-analysis-success">
          <h3>Scene与阅读旅程已完成</h3>
          <ul>
            <li data-testid="chapter-analysis-scene-count">
                Scene 数量：{(run.total_scene_count ?? counts.total) || "—"}
            </li>
            <li data-testid="chapter-analysis-coverage">
              覆盖：
              {typeof run.scene_analysis_coverage_rate === "number"
                ? `${Math.round(run.scene_analysis_coverage_rate * 100)}%`
                : "已完成"}
            </li>
            <li data-testid="chapter-analysis-journey-flag">
              读者旅程：{hasJourney ? "已有可视化" : "已完成"}
            </li>
            {run.completed_at && (
              <li data-testid="chapter-analysis-completed-at">
                完成时间：{new Date(run.completed_at).toLocaleString()}
              </li>
            )}
          </ul>
          <div className="chapter-analysis-success-actions">
            {onViewResults ? (
              <button
                type="button"
                className="primary"
                data-testid="chapter-analysis-open-results"
                onClick={onViewResults}
              >
                查看正文与读者旅程
              </button>
            ) : (
              <a
                className="primary"
                data-testid="chapter-analysis-open-results"
                href={`/analysis-runs/${run.id}/results?tab=reader-journey`}
              >
                查看正文与读者旅程
              </a>
            )}
            {onContinueReading && (
              <button
                type="button"
                className="secondary"
                data-testid="chapter-analysis-continue-reading"
                onClick={onContinueReading}
              >
                继续阅读正文
              </button>
            )}
          </div>
        </div>
      )}

      {uiState === "running" && (
        <p className="muted" data-testid="chapter-analysis-running-help">
          分析在后台继续进行。可切换章节阅读；返回本章后将恢复进度显示。
        </p>
      )}
    </aside>
  );
}
