/**
 * Live Mock Run controls — consumes backend allowed_actions only.
 * On failure, callers must re-fetch backend state (never force local status).
 */

import { useState } from "react";
import { Button } from "../../../../components/ui/Button";
import type { MockWholeBookRunClient } from "../client/mockWholeBookRunClient";
import type { MockWholeBookRunViewDto } from "../client/types";
import { presentMockRunError } from "../client/errors";
import { createOperationIdempotencyKey } from "./idempotency";

export type MockRunControlsProps = {
  client: Pick<
    MockWholeBookRunClient,
    "pause" | "resume" | "cancel" | "retryStage" | "get"
  >;
  view: MockWholeBookRunViewDto;
  onViewChange: (next: MockWholeBookRunViewDto) => void;
  onFeedback?: (message: string) => void;
};

export function MockRunControls({
  client,
  view,
  onViewChange,
  onFeedback,
}: MockRunControlsProps) {
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [retryStageKey, setRetryStageKey] = useState<string>(
    () => view.stages.find((s) => s.status === "failed")?.stage_key ?? "",
  );

  const pauseAllowed = view.allowed_actions.includes("pause");
  const resumeAllowed = view.allowed_actions.includes("resume");
  const cancelAllowed = view.allowed_actions.includes("cancel");
  const retryAllowed =
    view.allowed_actions.includes("retry") ||
    view.stages.some((s) => s.allowed_actions.includes("retry"));

  const failedStages = view.stages.filter((s) => s.status === "failed");
  const selectedFailed = failedStages.find((s) => s.stage_key === retryStageKey);
  const downstreamImpact = selectedFailed
    ? view.stages
        .filter((s) => s.order > selectedFailed.order)
        .map((s) => s.display_name || s.stage_key)
    : [];

  const setMsg = (msg: string) => {
    setFeedback(msg);
    onFeedback?.(msg);
  };

  const refreshAfter = async () => {
    const fresh = await client.get(view.run_id);
    onViewChange(fresh);
    return fresh;
  };

  const runAction = async (
    action: "pause" | "resume" | "cancel" | "retry",
    fn: () => Promise<unknown>,
  ) => {
    if (busyAction) return;
    setBusyAction(action);
    try {
      await fn();
      await refreshAfter();
      setMsg(`${action} 已提交；状态已从后端刷新。`);
      if (action === "cancel") setConfirmCancel(false);
    } catch (error) {
      const presented = presentMockRunError(error);
      setMsg(`${presented.title}: ${presented.message}`);
      try {
        await refreshAfter();
      } catch {
        // keep previous view; fail-closed
      }
    } finally {
      setBusyAction(null);
    }
  };

  return (
    <section
      className="wb-mock-lab__section"
      data-testid="mock-run-controls"
      aria-labelledby="mock-run-controls-heading"
    >
      <h2 id="mock-run-controls-heading">运行控制（Mock Lab）</h2>
      <p className="wb-mock-lab__hint">
        仅当后端 allowed_actions 包含对应动作时可用。失败后重新拉取后端状态，不在本地强制改状态。
      </p>

      <div className="wb-run-actions" role="toolbar" aria-label="Mock 运行控制">
        <Button
          type="button"
          variant="secondary"
          disabled={!pauseAllowed || busyAction != null}
          title={
            !pauseAllowed
              ? "allowed_actions 不含 pause"
              : busyAction
                ? "操作进行中"
                : "暂停"
          }
          aria-disabled={!pauseAllowed || busyAction != null}
          data-testid="mock-action-pause"
          onClick={() =>
            void runAction("pause", () =>
              client.pause(view.run_id, {
                operation_idempotency_key: createOperationIdempotencyKey(
                  "pause",
                  view.run_id,
                ),
                expected_state: view.status,
                expected_version: view.version,
              }),
            )
          }
        >
          {busyAction === "pause" ? "暂停中…" : "暂停"}
        </Button>

        <Button
          type="button"
          variant="secondary"
          disabled={!resumeAllowed || busyAction != null}
          title={
            !resumeAllowed
              ? "allowed_actions 不含 resume（需 paused/interrupted）"
              : "恢复同一 run_id；已完成 Stage 不重跑"
          }
          data-testid="mock-action-resume"
          onClick={() =>
            void runAction("resume", () =>
              client.resume(view.run_id, {
                operation_idempotency_key: createOperationIdempotencyKey(
                  "resume",
                  view.run_id,
                ),
                expected_state: view.status,
                expected_version: view.version,
              }),
            )
          }
        >
          {busyAction === "resume" ? "恢复中…" : "恢复"}
        </Button>

        <div className="wb-mock-lab__retry-group">
          <label htmlFor="mock-retry-stage">
            重试失败 Stage
            <select
              id="mock-retry-stage"
              data-testid="mock-retry-stage-select"
              value={retryStageKey}
              disabled={!retryAllowed || failedStages.length === 0 || busyAction != null}
              onChange={(e) => setRetryStageKey(e.target.value)}
            >
              <option value="">选择失败阶段</option>
              {failedStages.map((s) => (
                <option key={s.stage_key} value={s.stage_key}>
                  {s.display_name || s.stage_key}
                </option>
              ))}
            </select>
          </label>
          {downstreamImpact.length > 0 ? (
            <p className="wb-mock-lab__warn" data-testid="retry-downstream-impact">
              下游可能受影响：{downstreamImpact.join("、")}
            </p>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            disabled={
              !retryAllowed || !retryStageKey || busyAction != null
            }
            title={
              !retryAllowed
                ? "allowed_actions 不含 retry"
                : !retryStageKey
                  ? "请指定失败 Stage（不提供全部无差别重跑）"
                  : "仅重试所选失败 Stage"
            }
            data-testid="mock-action-retry"
            onClick={() =>
              void runAction("retry", () =>
                client.retryStage(view.run_id, retryStageKey, {
                  operation_idempotency_key: createOperationIdempotencyKey(
                    "retry",
                    view.run_id,
                    retryStageKey,
                  ),
                  expected_state: view.status,
                  expected_version: view.version,
                  stage_key: retryStageKey,
                }),
              )
            }
          >
            {busyAction === "retry" ? "重试中…" : "重试失败阶段"}
          </Button>
        </div>

        {!confirmCancel ? (
          <Button
            type="button"
            variant="danger"
            disabled={!cancelAllowed || busyAction != null}
            title={
              !cancelAllowed
                ? "allowed_actions 不含 cancel"
                : "取消需要二次确认；候选结果会保留"
            }
            data-testid="mock-action-cancel"
            onClick={() => setConfirmCancel(true)}
          >
            取消
          </Button>
        ) : (
          <div className="wb-cancel-confirm" data-testid="mock-cancel-confirm">
            <p role="alert">
              确认取消？已完成候选结果会保留；不会删除 Book / Snapshot / 用户文件。
            </p>
            <Button
              type="button"
              variant="danger"
              disabled={busyAction != null}
              data-testid="mock-action-cancel-confirm"
              onClick={() =>
                void runAction("cancel", () =>
                  client.cancel(view.run_id, {
                    operation_idempotency_key: createOperationIdempotencyKey(
                      "cancel",
                      view.run_id,
                    ),
                    expected_state: view.status,
                    expected_version: view.version,
                    confirm_cancel: true,
                  }),
                )
              }
            >
              {busyAction === "cancel" ? "取消中…" : "确认取消"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              data-testid="mock-action-cancel-abort"
              onClick={() => setConfirmCancel(false)}
            >
              返回
            </Button>
          </div>
        )}
      </div>

      {feedback ? (
        <p
          className="wb-mock-lab__feedback"
          role="status"
          data-testid="mock-action-feedback"
        >
          {feedback}
        </p>
      ) : null}
    </section>
  );
}
