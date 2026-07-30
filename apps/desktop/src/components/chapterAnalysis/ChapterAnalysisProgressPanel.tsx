import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { analysisApi } from "../../services/analysisApi";
import { settingsApi } from "../../services/settingsApi";
import { formatCny, formatTokenCount } from "../analysis/analysisDisplayLabels";
import type { Run } from "../../types";
import {
  shouldShowUnifiedRecovery,
  UnifiedAnalysisRecoveryCard,
} from "./UnifiedAnalysisRecoveryCard";
import { isJourneyActivelyRunning } from "../../services/journeyActiveRecoveryGuard";
import { ChapterAnalysisFailureCard } from "./ChapterAnalysisFailureCard";
import { ChapterAnalysisStatusBadge } from "./ChapterAnalysisStatusBadge";
import {
  budgetSummary,
  currentWorkLabel,
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
  /** When set, overrides AnalysisRun-based elapsed (Reader Journey clock). */
  elapsedOverride?: string | null;
  /** Optional progress counts from the selected journey run. */
  progressOverride?: { current: number; total: number } | null;
  /** Optional status label override (e.g. journey failed copy). */
  statusLabelOverride?: string | null;
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
  /** CHG-018: suppress recovery while journey generation is active. */
  journeyPageActive?: boolean;
  journeyStatus?: string | null;
};

export function ChapterAnalysisProgressPanel({
  run,
  uiState,
  chapterTitle,
  reconnectHint,
  canResume,
  elapsedOverride,
  progressOverride,
  statusLabelOverride,
  onResume,
  onReanalyze,
  onReviewBoundary,
  onDismiss,
  onContinueReading,
  onViewResults,
  onContinueReaderJourney,
  onBudgetContinued,
  journeyPageActive = false,
  journeyStatus = null,
}: Props) {
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumeError, setResumeError] = useState<string>();
  const [hasJourney, setHasJourney] = useState(false);
  const counts = progressOverride ?? progressCounts(run);
  const pct =
    counts.total > 0 ? Math.min(100, Math.round((counts.current / counts.total) * 100)) : 0;
  const steps = stageSteps(uiState, run);
  const cost = run ? budgetSummary(run) : null;
  const elapsed =
    elapsedOverride !== undefined ? elapsedOverride : run ? elapsedLabel(run) : null;
  const currentWork = currentWorkLabel(uiState, run);
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
    uiState !== "succeeded" &&
    (uiState === "running" ||
      uiState === "partial" ||
      uiState === "boundary_review_required" ||
      uiState === "awaiting_budget_adjustment" ||
      uiState === "aborted_by_limit" ||
      uiState === "provider_recovery" ||
      uiState === "reader_journey_processing" ||
      uiState === "awaiting_reader_journey_start");

  const meterDetail =
    uiState === "reader_journey_processing"
      ? counts.total > 0
        ? `正在整合 ${counts.total} 个场景`
        : "正在生成阅读旅程"
      : uiState === "awaiting_reader_journey_start"
        ? counts.total > 0
          ? `场景 ${counts.current} / ${counts.total}`
          : "场景已确认，等待生成阅读旅程"
        : counts.total > 0
          ? `场景 ${counts.current} / ${counts.total}`
          : uiStateLabel(uiState);

  const liveJourneyStatus = journeyStatus || run?.journey_status || null;
  const journeyActiveNow =
    journeyPageActive ||
    isJourneyActivelyRunning(liveJourneyStatus) ||
    uiState === "reader_journey_processing";
  const showRecovery = Boolean(run) && shouldShowUnifiedRecovery(uiState) && !journeyActiveNow;

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

      {(statusLabelOverride || currentWork) && (
        <p className="chapter-analysis-current-work" data-testid="chapter-analysis-current-work">
          {statusLabelOverride || currentWork}
        </p>
      )}

      <ol className="chapter-analysis-stages" data-testid="chapter-analysis-stages">
        {steps.map((step) => (
          <li key={step.id} data-tone={step.tone} data-testid={`chapter-analysis-stage-${step.id}`}>
            <span className="stage-mark" aria-hidden>
              {step.tone === "done"
                ? "✓"
                : step.tone === "active"
                  ? "●"
                  : step.tone === "failed"
                    ? "!"
                    : "○"}
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
          <p data-testid="chapter-analysis-count">{meterDetail}</p>
          {elapsed && <p data-testid="chapter-analysis-elapsed">已用时间 {elapsed}</p>}
          {cost && <p data-testid="chapter-analysis-budget">{cost}</p>}
        </div>
      )}

      {run && (
        <details className="chapter-analysis-fold" data-testid="chapter-analysis-usage-details">
          <summary>用量详情</summary>
          <dl className="chapter-analysis-run-meta">
            <div>
              <dt>场景进度</dt>
              <dd data-testid="chapter-analysis-scene-progress">
                {counts.total > 0 ? `${counts.current} / ${counts.total}` : "—"}
              </dd>
            </div>
            <div>
              <dt>当前场景</dt>
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
                  ? formatTokenCount(usage.total_tokens)
                  : typeof run.budget_remaining?.tokens === "number"
                    ? `剩余 ${formatTokenCount(run.budget_remaining.tokens)}`
                    : "—"}
              </dd>
            </div>
            <div>
              <dt>费用</dt>
              <dd data-testid="chapter-analysis-today-cost">
                {typeof usage?.estimated_cost === "number"
                  ? formatCny(usage.estimated_cost)
                  : typeof run.budget_remaining?.estimated_cost === "number"
                    ? `剩余 ${formatCny(run.budget_remaining.estimated_cost)}`
                    : "—"}
              </dd>
            </div>
          </dl>
        </details>
      )}

      {run && (
        <details className="chapter-analysis-fold" data-testid="chapter-analysis-tech-fold">
          <summary>技术详情</summary>
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
              <dt>读者旅程</dt>
              <dd data-testid="chapter-analysis-journey-stage">
                {readerJourneyStageLabel(run, uiState)}
              </dd>
            </div>
            <div>
              <dt>状态</dt>
              <dd data-testid="chapter-analysis-status-text">
                {statusLabelOverride || uiStateLabel(uiState)}
              </dd>
            </div>
          </dl>
        </details>
      )}

      {uiState === "boundary_review_required" && (
        <div className="chapter-analysis-boundary" data-testid="chapter-analysis-boundary">
          <p>请确认场景划分后继续分析。</p>
          <button
            type="button"
            className="primary"
            data-testid="chapter-analysis-review-boundary"
            onClick={onReviewBoundary}
          >
            确认场景划分
          </button>
        </div>
      )}

      {showRecovery && run ? (
        <UnifiedAnalysisRecoveryCard
          run={run}
          variant="card"
          journeyStatus={liveJourneyStatus}
          journeyPageActive={journeyActiveNow}
          onContinued={onBudgetContinued}
          onLater={onDismiss}
        />
      ) : null}

      {(uiState === "failed" || uiState === "partial") &&
        run &&
        !showRecovery && (
        <ChapterAnalysisFailureCard
          run={run}
          canResume={Boolean(canResume)}
          resumeBusy={resumeBusy}
          onResume={handleResume}
          onLater={onDismiss}
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

      {uiState === "awaiting_reader_journey_start" && run && !journeyActiveNow && (
        <div
          className="chapter-analysis-success"
          data-testid="chapter-analysis-journey-pending"
        >
          <h3>场景分析已完成，阅读旅程尚未生成</h3>
          <p>任务 #{run.id} 的场景结果已保留。可继续生成阅读旅程，不会重新分析场景。</p>
          {onContinueReaderJourney && (
            <button
              type="button"
              className="primary"
              data-testid="chapter-analysis-continue-journey"
              onClick={onContinueReaderJourney}
            >
              继续生成阅读旅程
            </button>
          )}
        </div>
      )}

      {uiState === "reader_journey_processing" && run && (
        <div
          className="chapter-analysis-success"
          data-testid="chapter-analysis-journey-processing"
        >
          <h3>正在生成阅读旅程</h3>
          <p>任务 #{run.id} 保持不变；任务中心可同步查看进度。</p>
          {onViewResults && (
            <button
              type="button"
              className="secondary"
              data-testid="chapter-analysis-open-results"
              onClick={onViewResults}
            >
              查看场景结果
            </button>
          )}
        </div>
      )}

      {uiState === "succeeded" && run && (
        <div className="chapter-analysis-success" data-testid="chapter-analysis-success">
          <h3>分析完成</h3>
          <ul>
            <li data-testid="chapter-analysis-scene-count">
              场景数量：{(run.total_scene_count ?? counts.total) || "—"}
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
                查看场景结果
              </button>
            ) : (
              <button
                type="button"
                className="primary"
                data-testid="chapter-analysis-open-results"
                disabled
                title="请在章节工作台内查看场景结果"
              >
                查看场景结果
              </button>
            )}
            {hasJourney && onContinueReaderJourney && (
              <button
                type="button"
                className="secondary"
                data-testid="chapter-analysis-open-journey"
                onClick={onContinueReaderJourney}
              >
                查看阅读旅程
              </button>
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
