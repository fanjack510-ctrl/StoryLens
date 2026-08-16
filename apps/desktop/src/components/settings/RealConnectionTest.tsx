import { useState } from "react";
import { providersApi } from "../../services/providersApi";

type Preflight = {
  configured_model?: string;
  max_output_tokens?: number;
  estimated_cost?: number | null;
  currency?: string;
  remaining_requests?: number;
  remaining_tokens?: number;
  remaining_estimated_cost?: number;
  within_budget?: boolean;
  blockers?: string[];
};

/**
 * 真实连接测试 — the one diagnostic that actually spends money.
 *
 * Salvaged from the deleted /providers page, which was a second, unreachable-by-design copy
 * of AI configuration. This is the part of it worth keeping: 验证连接 in the AI tab checks
 * that the service is reachable and configured, while this sends a real (tiny, original,
 * novel-text-free) request and reports what it cost. Two different questions.
 *
 * It keeps the confirmation step: a button that spends money without saying how much first
 * is a button people learn to fear.
 */
export function RealConnectionTest({ provider }: { provider: string }) {
  const [state, setState] = useState<"idle" | "confirming" | "running" | "done" | "failed">("idle");
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string>("");

  const open = async () => {
    setState("confirming");
    setPreflight(null);
    setResult(null);
    setError("");
    try {
      setPreflight(await providersApi.connectionTestPreflight(provider));
    } catch (err: any) {
      setError(err?.message || "读取预算失败");
    }
  };

  const run = async () => {
    setState("running");
    setError("");
    try {
      const checked: Preflight = await providersApi.connectionTestPreflight(provider);
      setPreflight(checked);
      if (checked.within_budget === false) {
        setState("failed");
        setError(`预算或配置门禁未通过：${(checked.blockers || []).join("、") || "未知原因"}`);
        return;
      }
      setResult(await providersApi.testConnection(provider, checked.max_output_tokens || 32));
      setState("done");
    } catch (err: any) {
      setState("failed");
      setError(err?.message || "连接测试失败");
    }
  };

  return (
    <details className="advanced-section" data-testid="advanced-real-connection-test">
      <summary>真实连接测试（会产生少量费用）</summary>
      <p className="hint">
        向云端模型发送一条原创最小 JSON 请求，<b>不发送小说正文</b>，可能产生少量 Token 费用。
      </p>
      {state === "idle" || state === "done" || state === "failed" ? (
        <button type="button" onClick={() => void open()} data-testid="real-connection-test-open">
          真实连接测试
        </button>
      ) : null}

      {state === "confirming" && (
        <div role="dialog" aria-label="执行真实连接测试" data-testid="real-connection-test-confirm">
          <dl className="settings-status-meta">
            <div>
              <dt>Provider</dt>
              <dd>
                <code className="settings-tech-id">{provider}</code>
              </dd>
            </div>
            <div>
              <dt>模型</dt>
              <dd>
                <code className="settings-tech-id">{preflight?.configured_model || "读取中…"}</code>
              </dd>
            </div>
            <div>
              <dt>预计费用</dt>
              <dd>
                {preflight
                  ? preflight.estimated_cost == null
                    ? "无法计算（缺少计价信息）"
                    : `${preflight.estimated_cost} ${preflight.currency || ""}`
                  : "读取中…"}
              </dd>
            </div>
            <div>
              <dt>剩余预算</dt>
              <dd>
                {preflight
                  ? `${preflight.remaining_requests ?? "—"} 请求 / ${preflight.remaining_tokens ?? "—"} Token`
                  : "读取中…"}
              </dd>
            </div>
          </dl>
          <button type="button" onClick={() => setState("idle")}>
            取消
          </button>
          <button
            type="button"
            className="primary"
            onClick={() => void run()}
            data-testid="real-connection-test-confirm-run"
          >
            确认并测试
          </button>
        </div>
      )}

      {state === "running" && <p>正在测试…</p>}
      {error && (
        <p role="alert" data-testid="real-connection-test-error">
          {error}
        </p>
      )}
      {state === "done" && (
        <pre data-testid="real-connection-test-result">{JSON.stringify(result, null, 2)}</pre>
      )}
    </details>
  );
}
