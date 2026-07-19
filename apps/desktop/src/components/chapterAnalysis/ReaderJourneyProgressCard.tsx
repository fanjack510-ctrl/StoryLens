import type { ReaderJourneyProgress } from "../../types";
import "./chapterAnalysis.css";

type Props = {
  analysisRunId: number;
  progress: ReaderJourneyProgress | null | undefined;
  loading?: boolean;
  errorMessage?: string | null;
  onViewTaskDetails: () => void;
};

export function ReaderJourneyProgressCard({
  analysisRunId,
  progress,
  loading,
  errorMessage,
  onViewTaskDetails,
}: Props) {
  const total = progress?.total_scene_count ?? 0;
  const done = progress?.completed_scene_count ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const failed =
    progress?.status === "failed" ||
    progress?.status === "scene_profiles_partial" ||
    progress?.status === "budget_blocked";

  return (
    <section
      className="reader-journey-progress-card"
      data-testid="reader-journey-progress-card"
      data-status={progress?.status || (loading ? "loading" : "unknown")}
    >
      <header>
        <h2 data-testid="reader-journey-progress-title">正在生成阅读旅程</h2>
        <p>
          保持 AnalysisRun #{analysisRunId}
          ，复用已有 Scene 分析结果；离开本页后任务仍会继续。
        </p>
      </header>
      {progress && (
        <dl data-testid="reader-journey-progress-meta">
          <div>
            <dt>JourneyRun</dt>
            <dd>#{progress.journey_run_id}</dd>
          </div>
          <div>
            <dt>阶段</dt>
            <dd data-testid="reader-journey-progress-stage">
              {progress.current_stage || progress.status}
            </dd>
          </div>
          <div>
            <dt>Scene Profiles</dt>
            <dd data-testid="reader-journey-progress-scenes">
              {done} / {total}
            </dd>
          </div>
          <div>
            <dt>Phase</dt>
            <dd>{progress.phase_count ?? 0}</dd>
          </div>
        </dl>
      )}
      <div className="reader-journey-progress-meter" data-testid="reader-journey-progress-meter">
        <div className="reader-journey-progress-meter-bar">
          <span style={{ width: `${pct}%` }} />
        </div>
        <p>
          {loading && !progress
            ? "正在连接进度…"
            : total > 0
              ? `${done} / ${total}`
              : progress?.status || "处理中"}
        </p>
      </div>
      {(failed || errorMessage) && (
        <p className="notice error" data-testid="reader-journey-progress-error">
          {errorMessage ||
            progress?.user_error_message ||
            progress?.root_error_message ||
            progress?.root_error_code ||
            "阅读旅程生成失败，可只重试旅程，无需重新分析整章。"}
        </p>
      )}
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
