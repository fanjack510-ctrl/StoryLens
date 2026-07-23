import type { WholeBookStageProgressDto } from "../../contracts/runView";
import { Button } from "../../../../components/ui/Button";

export type WholeBookStageProgressListProps = {
  stages: readonly WholeBookStageProgressDto[];
  currentStage: string | null;
  onRetryStage?: (stageKey: string) => void;
};

export function WholeBookStageProgressList({
  stages,
  currentStage,
  onRetryStage,
}: WholeBookStageProgressListProps) {
  const sorted = [...stages].sort((a, b) => a.order - b.order);

  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-stage-progress-list"
      aria-labelledby="wb-stage-progress-heading"
    >
      <h2 id="wb-stage-progress-heading">阶段进度</h2>
      <ol className="wb-stage-progress">
        {sorted.map((stage) => {
          const isCurrent = stage.stage_key === currentStage;
          const canRetry =
            stage.status === "failed" &&
            stage.allowed_actions.includes("retry") &&
            Boolean(onRetryStage);
          return (
            <li
              key={stage.stage_key}
              className="wb-stage-progress__item"
              data-testid={`stage-progress-${stage.stage_key}`}
              data-status={stage.status}
              data-current={isCurrent ? "true" : "false"}
              aria-current={isCurrent ? "step" : undefined}
            >
              <header className="wb-stage-progress__header">
                <span className="wb-stage-progress__title">
                  {stage.display_name}
                </span>
                <span
                  className="wb-status-pill"
                  data-status={stage.status}
                  aria-label={`状态 ${stage.status}`}
                >
                  {stage.status}
                </span>
              </header>
              <p className="wb-stage-progress__meta">
                顺序 {stage.order}
                {" · "}
                {stage.required ? "必需" : "可选"}
                {" · "}
                可恢复 {stage.resumable ? "是" : "否"} / 可重试{" "}
                {stage.retryable ? "是" : "否"}
                {" · "}
                尝试 {stage.attempt_count}
              </p>
              {stage.progress_percent != null ? (
                <p>进度（诚实值）：{stage.progress_percent}%</p>
              ) : (
                <p>进度：阶段状态（无精确百分比）</p>
              )}
              {stage.produced_module_keys.length > 0 ? (
                <p>产出模块：{stage.produced_module_keys.join(", ")}</p>
              ) : null}
              {stage.error_message ? (
                <p className="wb-run-ux__warn wb-wrap" role="alert">
                  {stage.error_code}: {stage.error_message}
                </p>
              ) : null}
              {canRetry ? (
                <Button
                  type="button"
                  variant="secondary"
                  size="small"
                  data-testid={`retry-stage-${stage.stage_key}`}
                  onClick={() => onRetryStage?.(stage.stage_key)}
                >
                  重试此失败阶段
                </Button>
              ) : null}
              <span className="wb-visually-hidden">
                阶段键 {stage.stage_key}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
