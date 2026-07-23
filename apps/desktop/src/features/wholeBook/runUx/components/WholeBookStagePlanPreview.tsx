import type { StagePlanPreviewRow } from "../types";

export type WholeBookStagePlanPreviewProps = {
  rows: readonly StagePlanPreviewRow[];
};

/**
 * Displays backend/fixture stage_plan. No prompts, model params, credentials, or fake tokens.
 */
export function WholeBookStagePlanPreview({ rows }: WholeBookStagePlanPreviewProps) {
  const sorted = [...rows].sort((a, b) => a.order - b.order);

  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-stage-plan-preview"
      aria-labelledby="wb-stage-plan-heading"
    >
      <h2 id="wb-stage-plan-heading">阶段计划预览</h2>
      <p className="wb-run-ux__hint">
        以下为信息性计划，不执行。费用 / Token / 耗时均为<strong>估算</strong>，非精确值。
      </p>
      {sorted.length === 0 ? (
        <p role="status">暂无阶段计划</p>
      ) : (
        <ol className="wb-stage-plan">
          {sorted.map((row) => (
            <li
              key={row.stage_key}
              className="wb-stage-plan__item"
              data-testid={`stage-plan-${row.stage_key}`}
              data-auto-filled={row.auto_filled ? "true" : "false"}
              data-required={row.required ? "true" : "false"}
            >
              <header className="wb-stage-plan__header">
                <span className="wb-stage-plan__order">#{row.order}</span>
                <span className="wb-stage-plan__title">{row.display_name}</span>
                {row.auto_filled ? (
                  <span className="wb-chip wb-chip--auto">自动补齐</span>
                ) : null}
                {row.required ? (
                  <span className="wb-chip">必需</span>
                ) : (
                  <span className="wb-chip">可选</span>
                )}
              </header>
              {row.description ? (
                <p className="wb-stage-plan__desc">{row.description}</p>
              ) : null}
              <dl className="wb-stage-plan__meta">
                <div>
                  <dt>阶段键</dt>
                  <dd>
                    <code>{row.stage_key}</code>
                  </dd>
                </div>
                <div>
                  <dt>可恢复 / 可重试</dt>
                  <dd>
                    {row.resumable == null ? "—" : row.resumable ? "是" : "否"}
                    {" / "}
                    {row.retryable == null ? "—" : row.retryable ? "是" : "否"}
                  </dd>
                </div>
                <div>
                  <dt>依赖</dt>
                  <dd>
                    {row.dependencies && row.dependencies.length > 0
                      ? row.dependencies.join(", ")
                      : "无"}
                  </dd>
                </div>
                <div>
                  <dt>费用等级（估算）</dt>
                  <dd>{row.estimated_cost_class}</dd>
                </div>
                <div>
                  <dt>产出模块</dt>
                  <dd>
                    {row.produced_module_keys.length > 0
                      ? row.produced_module_keys.join(", ")
                      : "—"}
                  </dd>
                </div>
              </dl>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
