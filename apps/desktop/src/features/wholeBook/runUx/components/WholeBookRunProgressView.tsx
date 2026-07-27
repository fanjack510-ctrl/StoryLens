import { mockRunActionAdapter } from "../mockRunActionAdapter";
import type { WholeBookRunViewState } from "../../contracts/runView";
import type { MockRunActionResult } from "../types";
import { RUN_STATUS_LABELS } from "../labels";
import { WholeBookStageProgressList } from "./WholeBookStageProgressList";
import { WholeBookPartialResultNotice } from "./WholeBookPartialResultNotice";
import { WholeBookRunActionBar } from "./WholeBookRunActionBar";

export type WholeBookRunProgressViewProps = {
  view: WholeBookRunViewState;
  onViewChange: (next: WholeBookRunViewState) => void;
  onActionResult?: (result: MockRunActionResult) => void;
};

export function WholeBookRunProgressView({
  view,
  onViewChange,
  onActionResult,
}: WholeBookRunProgressViewProps) {
  const failedStage =
    view.stages.find((s) => s.status === "failed")?.stage_key ?? null;
  const statusLabel = RUN_STATUS_LABELS[view.status];

  const handleRetryStage = (stageKey: string) => {
    const { result, next } = mockRunActionAdapter.apply(view, "retry", {
      stage_key: stageKey,
    });
    onActionResult?.(result);
    if (result.ok) onViewChange(next);
  };

  return (
    <div
      className="wb-run-ux__panel"
      data-testid="whole-book-run-progress-view"
      data-status={view.status}
      data-interrupted={view.status === "interrupted" ? "true" : "false"}
      data-failed={view.status === "failed" ? "true" : "false"}
      data-paused={view.status === "paused" ? "true" : "false"}
    >
      <header className="wb-run-ux__header">
        <h1>整书分析运行进度（原型）</h1>
        <p
          className="wb-run-ux__status-line"
          role="status"
          aria-live="polite"
          data-testid="run-status-text"
        >
          总状态：<strong>{statusLabel}</strong>
          <span className="wb-visually-hidden">（{view.status}）</span>
          {view.current_stage ? (
            <>
              {" · "}
              当前阶段：{view.current_stage}
            </>
          ) : null}
        </p>
        <p className="wb-run-ux__hint">
          paused ≠ failed；interrupted ≠ failed。不伪造精确剩余时间。
        </p>
      </header>

      <dl className="wb-kv" data-testid="run-summary">
        <div>
          <dt>Run / Book / Snapshot</dt>
          <dd>
            #{view.run_id} / #{view.book_id} / #{view.snapshot_id}
          </dd>
        </div>
        <div>
          <dt>模式</dt>
          <dd>{view.analysis_mode}</dd>
        </div>
        <div>
          <dt>进度</dt>
          <dd>
            {view.progress_percent == null
              ? "无精确百分比（按阶段状态）"
              : `${view.progress_percent}%`}
          </dd>
        </div>
        <div>
          <dt>Token / 费用汇总</dt>
          <dd>
            input={view.token_usage.input ?? "—"} · output=
            {view.token_usage.output ?? "—"} · cost=
            {view.cost == null ? "—" : view.cost}
          </dd>
        </div>
        <div>
          <dt>开始 / 更新</dt>
          <dd className="wb-wrap">
            {view.started_at ?? "—"} / {view.updated_at ?? "—"}
          </dd>
        </div>
        <div>
          <dt>预计剩余</dt>
          <dd>{view.estimated_remaining ?? "未估算（不伪造）"}</dd>
        </div>
        <div>
          <dt>allowed_actions</dt>
          <dd data-testid="allowed-actions">
            {view.allowed_actions.join(", ") || "（无）"}
          </dd>
        </div>
        <div>
          <dt>已完成 / 可查看 / 失败模块</dt>
          <dd className="wb-wrap">
            {view.completed_modules.join(", ") || "无"}
            {" / "}
            {view.available_modules.join(", ") || "无"}
            {" / "}
            {view.failed_modules.join(", ") || "无"}
          </dd>
        </div>
      </dl>

      {view.blocking_issue ? (
        <div
          className="wb-blocking"
          role="alert"
          data-testid="run-blocking-issue"
        >
          阻断问题：{view.blocking_issue}
        </div>
      ) : null}

      <WholeBookPartialResultNotice
        available={view.partial_results_available}
        completedModules={view.completed_modules}
        failedModules={view.failed_modules}
        cancelled={view.status === "cancelled"}
      />

      <WholeBookStageProgressList
        stages={view.stages}
        currentStage={view.current_stage}
        onRetryStage={handleRetryStage}
      />

      <WholeBookRunActionBar
        view={view}
        onViewChange={onViewChange}
        onActionResult={onActionResult}
        retryStageKey={failedStage}
      />
    </div>
  );
}
