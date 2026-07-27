import { useState } from "react";
import { Button } from "../../../../components/ui/Button";
import type { WholeBookRunViewState } from "../../contracts/runView";
import type { MockRunActionResult } from "../types";
import { mockRunActionAdapter } from "../mockRunActionAdapter";
import { ACTION_LABELS } from "../labels";

export type WholeBookRunActionBarProps = {
  view: WholeBookRunViewState;
  onViewChange: (next: WholeBookRunViewState) => void;
  onActionResult?: (result: MockRunActionResult) => void;
  /** Optional failed stage for retry targeting */
  retryStageKey?: string | null;
};

/**
 * Pause / Resume / Retry / Cancel — consumes allowed_actions only.
 * Calls Mock adapter; never production run APIs.
 */
export function WholeBookRunActionBar({
  view,
  onViewChange,
  onActionResult,
  retryStageKey = null,
}: WholeBookRunActionBarProps) {
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [lastPreview, setLastPreview] = useState<string | null>(null);

  const run = (
    action: "pause" | "resume" | "retry" | "cancel",
    opts?: { stage_key?: string; confirmCancel?: boolean },
  ) => {
    const { result, next } = mockRunActionAdapter.apply(view, action, opts);
    setFeedback(result.message);
    setLastPreview(JSON.stringify(result.request_preview, null, 2));
    onActionResult?.(result);
    if (result.ok) {
      onViewChange(next);
      if (action === "cancel") setConfirmCancel(false);
    }
  };

  const pauseAllowed = view.allowed_actions.includes("pause");
  const resumeAllowed = view.allowed_actions.includes("resume");
  const cancelAllowed = view.allowed_actions.includes("cancel");
  const retryAllowed =
    view.allowed_actions.includes("retry") ||
    (retryStageKey
      ? view.stages.some(
          (s) =>
            s.stage_key === retryStageKey &&
            s.allowed_actions.includes("retry"),
        )
      : false);

  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-run-action-bar"
      aria-labelledby="wb-run-actions-heading"
    >
      <h2 id="wb-run-actions-heading">运行操作（Mock）</h2>
      <p className="wb-run-ux__hint">
        仅当后端/Fixture 的 allowed_actions 包含对应动作时可用。不调用真实生产运行
        API。
      </p>
      <div className="wb-run-actions" role="toolbar" aria-label="运行控制">
        <Button
          type="button"
          variant="secondary"
          disabled={!pauseAllowed}
          title={!pauseAllowed ? "allowed_actions 不含 pause" : ACTION_LABELS.pause}
          data-testid="action-pause"
          onClick={() => run("pause")}
        >
          暂停
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!resumeAllowed}
          title={
            !resumeAllowed
              ? "allowed_actions 不含 resume"
              : "从 paused / interrupted 恢复；已完成 Stage 不重跑"
          }
          data-testid="action-resume"
          onClick={() => run("resume")}
        >
          恢复
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!retryAllowed || !retryStageKey}
          title={
            !retryAllowed
              ? "allowed_actions 不含 retry"
              : !retryStageKey
                ? "请指定失败 Stage"
                : "仅重试失败 Stage；下游可能重新失效"
          }
          data-testid="action-retry"
          onClick={() =>
            run("retry", { stage_key: retryStageKey ?? undefined })
          }
        >
          重试失败阶段
        </Button>
        {!confirmCancel ? (
          <Button
            type="button"
            variant="danger"
            disabled={!cancelAllowed}
            title={
              !cancelAllowed
                ? "allowed_actions 不含 cancel"
                : "取消需要二次确认"
            }
            data-testid="action-cancel"
            onClick={() => setConfirmCancel(true)}
          >
            取消
          </Button>
        ) : (
          <div className="wb-cancel-confirm" data-testid="cancel-confirm">
            <p role="alert">
              确认取消？已完成候选结果会保留；不等于删除书籍或 Snapshot。
            </p>
            <Button
              type="button"
              variant="danger"
              data-testid="action-cancel-confirm"
              onClick={() => run("cancel", { confirmCancel: true })}
            >
              确认取消
            </Button>
            <Button
              type="button"
              variant="ghost"
              data-testid="action-cancel-abort"
              onClick={() => setConfirmCancel(false)}
            >
              返回
            </Button>
          </div>
        )}
      </div>
      {feedback ? (
        <p className="wb-run-ux__feedback" role="status" data-testid="action-feedback">
          {feedback}
        </p>
      ) : null}
      {lastPreview ? (
        <details data-testid="future-api-preview">
          <summary>未来 API 请求结构预览</summary>
          <pre className="wb-code-block">{lastPreview}</pre>
        </details>
      ) : null}
    </section>
  );
}
