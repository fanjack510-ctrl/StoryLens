export type WholeBookBlockingReasonsPanelProps = {
  blockingReasons: readonly string[];
  warnings?: readonly string[];
  /** Prefer effective; kept for backward-compatible prop name. */
  runCreationEnabled: boolean;
  backendRunCreationEnabled?: boolean;
  clientRunCreationEnabled?: boolean;
  effectiveRunCreationEnabled?: boolean;
};

export function WholeBookBlockingReasonsPanel({
  blockingReasons,
  warnings = [],
  runCreationEnabled,
  backendRunCreationEnabled,
  clientRunCreationEnabled,
  effectiveRunCreationEnabled,
}: WholeBookBlockingReasonsPanelProps) {
  const effective =
    effectiveRunCreationEnabled ?? runCreationEnabled;
  return (
    <section
      className="wb-run-ux__section"
      data-testid="whole-book-blocking-reasons"
      aria-labelledby="wb-blocking-heading"
    >
      <h2 id="wb-blocking-heading">启动条件</h2>
      <p
        className="wb-run-ux__status-line"
        data-testid="run-creation-enabled"
        role="status"
        aria-live="polite"
      >
        effective_run_creation_enabled：
        <strong>{effective ? "true" : "false"}</strong>
        {effective ? "" : "（当前阶段必须保持禁用）"}
      </p>
      <dl className="wb-kv" data-testid="run-creation-flag-breakdown">
        <div>
          <dt>backend_run_creation_enabled</dt>
          <dd>
            {String(
              backendRunCreationEnabled ?? runCreationEnabled ?? false,
            )}
          </dd>
        </div>
        <div>
          <dt>client_run_creation_enabled</dt>
          <dd>{String(clientRunCreationEnabled ?? false)}</dd>
        </div>
        <div>
          <dt>effective_run_creation_enabled</dt>
          <dd>{String(effective)}</dd>
        </div>
      </dl>
      {blockingReasons.length > 0 ? (
        <div className="wb-blocking" role="alert">
          <strong>阻断原因（后端）</strong>
          <ul data-testid="blocking-reasons-list">
            {blockingReasons.map((reason) => (
              <li key={reason} className="wb-blocking__item">
                {reason}
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p role="status">无阻断原因（仍可能因策略禁用真实启动）</p>
      )}
      {warnings.length > 0 ? (
        <div className="wb-warnings" data-testid="preflight-warnings">
          <strong>警告</strong>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
