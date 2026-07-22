import type { ReaderJourneyResult } from "../../types";
import {
  hasChartSafeJourneyNodes,
  hasUsableJourneyVisualization,
} from "./hasUsableJourneyVisualization";
import { ReaderJourneyWorkspace } from "./ReaderJourneyWorkspace";
import type { WorkspaceMainState } from "../../services/resolveWorkspaceLayout";

type Props = {
  bookId: number;
  chapterId: number | null;
  analysisRunId: number;
  journey: ReaderJourneyResult | null | undefined;
  mainContentState: WorkspaceMainState;
  onRetry: () => void;
  onReading: () => void;
  onViewScene?: () => void;
};

function JourneyActions({
  onReading,
  onViewScene,
}: {
  onReading: () => void;
  onViewScene?: () => void;
}) {
  return (
    <div className="chapter-result-error-actions">
      <button type="button" className="secondary" onClick={onReading}>
        返回正文阅读
      </button>
      {onViewScene ? (
        <button type="button" className="secondary" onClick={onViewScene}>
          查看场景结果
        </button>
      ) : null}
    </div>
  );
}

/**
 * Journey content for the unified Book workspace MainContentPane.
 * Does not embed the legacy standalone AnalysisResultsPage shell.
 */
export function WorkspaceJourneyPane({
  bookId,
  chapterId,
  analysisRunId,
  journey,
  mainContentState,
  onRetry,
  onReading,
  onViewScene,
}: Props) {
  if (mainContentState === "loading" || mainContentState === "idle") {
    return (
      <div className="workspace-journey-pane state" data-testid="workspace-journey-pane" data-state="loading">
        <strong>正在加载阅读旅程…</strong>
        <span className="secondary">
          book {bookId}
          {chapterId ? ` · chapter ${chapterId}` : ""} · run {analysisRunId}
        </span>
      </div>
    );
  }

  if (mainContentState === "pending_generation") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="pending_generation"
      >
        <strong>正在生成阅读旅程</strong>
        <span>可继续在「场景分析」查看已完成的 Scene，后台不会中断。</span>
        {onViewScene ? (
          <button type="button" className="secondary" onClick={onViewScene}>
            查看场景结果
          </button>
        ) : null}
      </div>
    );
  }

  if (mainContentState === "scope_mismatch") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="scope_mismatch"
      >
        <strong>当前分析结果与本章节不匹配</strong>
        <span>系统不会自动回退到其他 Run。</span>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  if (mainContentState === "request_error") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="request_error"
      >
        <strong>阅读旅程加载失败</strong>
        <div className="chapter-result-error-actions">
          <button type="button" className="primary" data-testid="workspace-journey-retry" onClick={onRetry}>
            重新加载
          </button>
          <button type="button" className="secondary" onClick={onReading}>
            返回正文阅读
          </button>
        </div>
      </div>
    );
  }

  if (mainContentState === "unavailable") {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>当前章节尚未生成阅读旅程</strong>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  const chartSafe = Boolean(journey && hasChartSafeJourneyNodes(journey));

  if (mainContentState === "invalid_artifact") {
    return (
      <div
        className="workspace-journey-pane"
        data-testid="workspace-journey-pane"
        data-state="invalid_artifact"
        data-book-id={bookId}
        data-chapter-id={chapterId ?? undefined}
        data-analysis-run={analysisRunId}
      >
        <div className="shell-banner" data-testid="workspace-journey-integrity-banner">
          <strong>阅读旅程结果校验未通过</strong>
          <span>检测到部分结论与当前正文不一致，受影响详情已暂停展示。</span>
        </div>
        <details data-testid="workspace-journey-tech-details">
          <summary>查看技术详情</summary>
          <p className="secondary">
            error_code=
            {(journey as { integrity?: { error_code?: string } } | null)?.integrity?.error_code ||
              (journey as { integrity_status?: string } | null)?.integrity_status ||
              "DATA_INTEGRITY_FAILED"}
            {" · "}
            analysis_run_id={analysisRunId}
            {journey?.journey_run_id ? ` · journey_run_id=${journey.journey_run_id}` : ""}
          </p>
        </details>
        {/* Never mount chart shell on redacted/incomplete nodes — that caused render crash. */}
        {chartSafe && journey?.visualization ? (
          <ReaderJourneyWorkspace
            visualization={journey.visualization}
            analysisRunId={analysisRunId}
            journeyRunId={journey.journey_run_id}
            onLocateEvidence={() => undefined}
          />
        ) : (
          <JourneyActions onReading={onReading} onViewScene={onViewScene} />
        )}
      </div>
    );
  }

  if (!journey || !hasUsableJourneyVisualization(journey) || !journey.visualization) {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="unavailable"
      >
        <strong>当前章节尚未生成阅读旅程</strong>
        <button type="button" className="secondary" onClick={onReading}>
          返回正文阅读
        </button>
      </div>
    );
  }

  if (!chartSafe) {
    return (
      <div
        className="workspace-journey-pane state"
        data-testid="workspace-journey-pane"
        data-state="invalid_artifact"
      >
        <strong>阅读旅程结果校验未通过</strong>
        <span>可视化结构不完整，暂不展示不可信内容。</span>
        <JourneyActions onReading={onReading} onViewScene={onViewScene} />
      </div>
    );
  }

  return (
    <div
      className="workspace-journey-pane"
      data-testid="workspace-journey-pane"
      data-state="ready"
      data-book-id={bookId}
      data-chapter-id={chapterId ?? undefined}
      data-analysis-run={analysisRunId}
    >
      <ReaderJourneyWorkspace
        visualization={journey.visualization}
        analysisRunId={analysisRunId}
        journeyRunId={journey.journey_run_id}
        onLocateEvidence={() => undefined}
      />
    </div>
  );
}
