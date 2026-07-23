/**
 * Mock Run progress panel — consumes backend view only.
 */

import { RUN_STATUS_LABELS } from "../../runUx/labels";
import { WholeBookStageProgressList } from "../../runUx/components/WholeBookStageProgressList";
import { WholeBookPartialResultNotice } from "../../runUx/components/WholeBookPartialResultNotice";
import type { MockWholeBookRunViewDto } from "../client/types";
import { LAB_UI_LABELS } from "../contracts/actions";
import { MockRunControls } from "../controls/MockRunControls";
import type { MockWholeBookRunClient } from "../client/mockWholeBookRunClient";

export type MockRunProgressPanelProps = {
  view: MockWholeBookRunViewDto;
  client: Pick<
    MockWholeBookRunClient,
    "pause" | "resume" | "cancel" | "retryStage" | "get"
  >;
  onViewChange: (next: MockWholeBookRunViewDto) => void;
  pollingHint?: string | null;
};

export function MockRunProgressPanel({
  view,
  client,
  onViewChange,
  pollingHint = null,
}: MockRunProgressPanelProps) {
  const statusLabel = RUN_STATUS_LABELS[view.status];

  return (
    <div
      className="wb-mock-lab__panel"
      data-testid="mock-run-progress-panel"
      data-status={view.status}
      data-mock="true"
      data-non-production="true"
      data-interrupted={view.status === "interrupted" ? "true" : "false"}
      data-failed={view.status === "failed" ? "true" : "false"}
      data-paused={view.status === "paused" ? "true" : "false"}
      data-cancelled={view.status === "cancelled" ? "true" : "false"}
    >
      <header className="wb-mock-lab__header">
        <p className="wb-mock-lab__badge" data-testid="mock-badge-progress">
          {LAB_UI_LABELS.mockBadge}
        </p>
        <h1>Mock 运行进度</h1>
        <p
          className="wb-mock-lab__status-line"
          role="status"
          aria-live="polite"
          data-testid="mock-run-status-text"
        >
          总状态：<strong>{statusLabel}</strong>
          <span className="wb-visually-hidden">（{view.status}）</span>
          {view.current_stage ? <> · 当前阶段：{view.current_stage}</> : null}
        </p>
        <p className="wb-mock-lab__hint">
          paused ≠ failed；interrupted ≠ failed；completed/cancelled 停止轮询。不伪造精确百分比。
        </p>
        {pollingHint ? (
          <p
            className="wb-mock-lab__poll-hint"
            role="status"
            aria-live="polite"
            data-testid="mock-polling-hint"
          >
            {pollingHint}
          </p>
        ) : null}
      </header>

      <dl className="wb-kv" data-testid="mock-run-summary">
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
          <dt>Synthetic Token / Cost</dt>
          <dd data-testid="synthetic-usage">
            （synthetic / non-billing）input=
            {view.token_usage.input ?? "—"} · output=
            {view.token_usage.output ?? "—"} · cost=
            {view.cost == null ? "—" : view.cost}
          </dd>
        </div>
        <div>
          <dt>已完成 / 可用 / 失败模块</dt>
          <dd data-testid="mock-module-lists">
            completed=[{view.completed_modules.join(", ") || "无"}] · available=[
            {view.available_modules.join(", ") || "无"}] · failed=[
            {view.failed_modules.join(", ") || "无"}]
          </dd>
        </div>
        <div>
          <dt>Warnings</dt>
          <dd className="wb-wrap" data-testid="mock-warnings">
            {view.warnings.length ? view.warnings.join("；") : "无"}
          </dd>
        </div>
        <div>
          <dt>Blocking issue</dt>
          <dd className="wb-wrap" data-testid="mock-blocking-issue">
            {view.blocking_issue ?? "无"}
          </dd>
        </div>
        <div>
          <dt>allowed_actions（仅后端）</dt>
          <dd data-testid="mock-allowed-actions">
            {view.allowed_actions.join(", ") || "无"}
          </dd>
        </div>
        <div>
          <dt>version / updated_at</dt>
          <dd>
            v{view.version} / {view.updated_at ?? "—"}
          </dd>
        </div>
      </dl>

      <WholeBookPartialResultNotice
        available={view.partial_results_available}
        completedModules={view.completed_modules}
        failedModules={view.failed_modules}
        cancelled={view.status === "cancelled"}
      />

      <WholeBookStageProgressList
        stages={view.stages}
        currentStage={view.current_stage}
        onRetryStage={undefined}
      />

      <MockRunControls
        client={client}
        view={view}
        onViewChange={onViewChange}
      />
    </div>
  );
}
