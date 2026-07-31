import type { ReaderJourneyProgress } from "../../types";
import { formatJourneyStatus } from "../readerJourney/journeyUiLabels";
import "./chapterAnalysis.css";

type Props = {
  analysisRunId: number;
  progress: ReaderJourneyProgress | null | undefined;
  loading?: boolean;
  errorMessage?: string | null;
  onViewTaskDetails: () => void;
};

/**
 * Only mount this card when CurrentJourneyExecutionState.phase === "running".
 * Must not accept a resuming boolean that can outlive terminal status.
 */
export function ReaderJourneyProgressCard({
  analysisRunId,
  progress,
  loading,
  errorMessage,
  onViewTaskDetails,
}: Props) {
  const total = progress?.total_scene_count ?? 0;
  const done = progress?.completed_scene_count ?? 0;
  const hasProgress = total > 0;
  const status = String(progress?.status || "");
  const statusLabel = formatJourneyStatus(progress?.status);
  const title =
    status === "starting" || status === "resuming" || status === "queued"
      ? "正在恢复阅读旅程"
      : "正在生成阅读旅程";
  const description =
    status === "starting" || status === "resuming" || status === "queued"
      ? "正在从已保存的进度继续，无需重复操作。"
      : "正在计算场景之间的情绪、节奏和阅读牵引变化。离开本页后任务仍会继续。";

  return (
    <section
      className="reader-journey-progress-card"
      data-testid="reader-journey-progress-card"
      data-status={progress?.status || (loading ? "loading" : "unknown")}
    >
      <header>
        <h2 data-testid="reader-journey-progress-title">{title}</h2>
        <p>{description}</p>
      </header>
      <div className="reader-journey-progress-meter" data-testid="reader-journey-progress-meter">
        <p data-testid="reader-journey-progress-scenes">
          {loading && !progress
            ? "正在连接进度…"
            : hasProgress
              ? `已处理 ${done} / ${total} 个场景`
              : "正在处理场景数据"}
        </p>
        {progress?.status ? (
          <p data-testid="reader-journey-progress-stage">状态：{statusLabel}</p>
        ) : null}
      </div>
      {errorMessage ? (
        <p className="notice error" data-testid="reader-journey-progress-error">
          {errorMessage}
        </p>
      ) : null}
      <details className="reader-journey-progress-tech" data-testid="reader-journey-progress-tech">
        <summary>技术详情</summary>
        <dl data-testid="reader-journey-progress-meta">
          <div>
            <dt>分析任务</dt>
            <dd>#{analysisRunId}</dd>
          </div>
          {progress?.journey_run_id != null ? (
            <div>
              <dt>旅程任务</dt>
              <dd>#{progress.journey_run_id}</dd>
            </div>
          ) : null}
          <div>
            <dt>原始状态</dt>
            <dd>{progress?.status || (loading ? "loading" : "—")}</dd>
          </div>
          {progress?.current_stage ? (
            <div>
              <dt>原始阶段</dt>
              <dd>{progress.current_stage}</dd>
            </div>
          ) : null}
          <div>
            <dt>阶段数</dt>
            <dd>{progress?.phase_count ?? 0}</dd>
          </div>
        </dl>
      </details>
      <button
        type="button"
        className="secondary"
        data-testid="reader-journey-progress-task-details"
        onClick={onViewTaskDetails}
      >
        查看任务详情
      </button>
    </section>
  );
}
