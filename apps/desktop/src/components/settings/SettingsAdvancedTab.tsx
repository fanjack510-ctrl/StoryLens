import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { settingsApi } from "../../services/settingsApi";
import { providersApi } from "../../services/providersApi";
import { AliyunForm } from "../providers/AliyunForm";
import { Badge, Loading } from "../common/States";
import { DEFAULT_AI_SERVICE_ID } from "../../services/aiServiceViewModel";

const ADVANCED_BUDGET_FIELDS = [
  ["cloud_max_input_tokens_per_request", "单请求最大输入 Token", 1],
  ["cloud_max_output_tokens_per_request", "单请求最大输出 Token", 1],
  ["cloud_max_requests_per_run", "AnalysisRun最大请求数", 1],
  ["cloud_daily_request_limit", "每日最大请求数", 1],
  ["cloud_daily_token_limit", "每日最大Token", 1],
] as const;

/**
 * Developer-only engineering panel.
 * Must not duplicate normal-mode cards (AI status / simple budget switches).
 */
export function SettingsAdvancedTab() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState(DEFAULT_AI_SERVICE_ID);
  const [budget, setBudget] = useState<any>(null);
  const [message, setMessage] = useState("");
  const [diagText, setDiagText] = useState("");
  const [transportResult, setTransportResult] = useState<any>();
  const [transportError, setTransportError] = useState("");

  const diagnostics = useQuery({ queryKey: ["diagnostics"], queryFn: settingsApi.diagnostics });
  const budgetQuery = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const pricing = useQuery({ queryKey: ["cloud-pricing"], queryFn: settingsApi.cloudPricing });
  const providers = useQuery({ queryKey: ["providers"], queryFn: providersApi.list });
  const routing = useQuery({ queryKey: ["routing"], queryFn: providersApi.routing });

  useEffect(() => {
    if (diagnostics.data) setDiagText(JSON.stringify(diagnostics.data, null, 2));
  }, [diagnostics.data]);
  useEffect(() => {
    if (budgetQuery.data) setBudget(budgetQuery.data);
  }, [budgetQuery.data]);

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["providers"] });
    void qc.invalidateQueries({ queryKey: ["routing"] });
    void qc.invalidateQueries({ queryKey: ["diagnostics"] });
  };

  const saveAdvancedBudget = async () => {
    setMessage("");
    if (
      !budget ||
      ADVANCED_BUDGET_FIELDS.some(
        ([key]) => !Number.isInteger(Number(budget[key])) || Number(budget[key]) <= 0,
      )
    ) {
      setMessage("保存失败：Token、请求数必须为正整数。");
      return;
    }
    try {
      await settingsApi.saveCloudBudget({ ...budget, currency: "CNY" });
      setMessage("高级预算参数已保存。");
      await qc.invalidateQueries({ queryKey: ["cloud-budget"] });
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    }
  };

  const runTransport = async () => {
    setTransportError("");
    try {
      setTransportResult(await providersApi.transportDiagnostic(selected));
    } catch (error: any) {
      setTransportResult(undefined);
      setTransportError(error?.message || "传输诊断失败");
    }
  };

  if (budgetQuery.isLoading || !budget) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  return (
    <div className="settings-advanced" data-testid="settings-panel-advanced">
      <article className="settings-panel">
        <header className="settings-panel-header">
          <h2>高级设置</h2>
          <p>Provider、路由、传输与系统诊断（仅开发者模式）。</p>
        </header>

        <section className="advanced-section">
          <h3>Provider 列表</h3>
          <div className="advanced-provider-list" data-testid="advanced-provider-list">
            {(providers.data || []).map((p) => (
              <button
                key={p.name}
                type="button"
                className={selected === p.name ? "selected" : ""}
                onClick={() => setSelected(p.name)}
              >
                <b>{p.name}</b>
                <small>{p.default_model}</small>
                <Badge tone={p.healthy ? "success" : "warning"}>
                  {p.health_state || (p.healthy ? "healthy" : "unhealthy")}
                </Badge>
              </button>
            ))}
          </div>
          <p>
            <Link to="/providers">打开完整模型与API页</Link>
          </p>
        </section>

        {selected.startsWith("aliyun_") && (
          <section className="advanced-section" data-testid="advanced-aliyun-form">
            <h3>工程配置 · {selected}</h3>
            <p className="hint">含 Workspace ID、Base URL、Region、Timeout、Retry、Max/Flash、自动路由。</p>
            <AliyunForm provider={selected} onSaved={refresh} />
          </section>
        )}

        <section className="advanced-section">
          <h3>传输诊断（DNS / TCP / TLS）</h3>
          <button type="button" onClick={runTransport}>
            运行传输诊断
          </button>
          {transportError && <p role="alert">{transportError}</p>}
          {transportResult && (
            <pre className="ai-diagnostics" data-testid="advanced-transport-result">
              {JSON.stringify(transportResult, null, 2)}
            </pre>
          )}
        </section>

        <section className="advanced-section">
          <h3>路由预览</h3>
          <div data-testid="advanced-routing-preview">
            {(routing.data || []).map((r: any) => (
              <div key={r.task}>
                <b>{r.task}</b> → {r.provider}
              </div>
            ))}
            {!routing.data?.length && <p className="muted">暂无路由数据</p>}
          </div>
        </section>

        <section className="advanced-section">
          <h3>高级预算闸门</h3>
          {ADVANCED_BUDGET_FIELDS.map(([key, label, min]) => (
            <label key={key} className="settings-field">
              <span>{label}</span>
              <input
                type="number"
                min={min}
                step={1}
                aria-label={label}
                value={budget[key]}
                onChange={(e) => setBudget({ ...budget, [key]: Number(e.target.value) })}
              />
            </label>
          ))}
          <label className="settings-switch-row">
            <span>价格未知时停止</span>
            <input
              type="checkbox"
              role="switch"
              className="settings-switch"
              checked={budget.cloud_stop_on_unknown_pricing}
              aria-label="价格未知时停止"
              onChange={(e) =>
                setBudget({ ...budget, cloud_stop_on_unknown_pricing: e.target.checked })
              }
            />
          </label>
          <p>价格版本：{pricing.data?.pricing_version || "无"}</p>
          {message && <p role="status">{message}</p>}
          <button type="button" className="primary" onClick={saveAdvancedBudget}>
            保存高级预算参数
          </button>
        </section>

        <section className="advanced-section">
          <h3>本地模型服务</h3>
          <div className="settings-actions">
            <button
              type="button"
              onClick={() =>
                confirm("启动本地模型可能造成较高GPU负载，确认使用safe配置？") &&
                providersApi.startLocal("safe").then(refresh)
              }
            >
              启动本地服务
            </button>
            <button type="button" onClick={() => providersApi.stopLocal().then(refresh)}>
              停止本地服务
            </button>
          </div>
        </section>

        <section className="advanced-section">
          <header className="settings-panel-header">
            <h3>系统诊断 JSON</h3>
            <button type="button" onClick={() => diagnostics.refetch()}>
              刷新
            </button>
          </header>
          {diagnostics.isLoading ? (
            <Loading />
          ) : (
            <>
              <textarea
                readOnly
                value={diagText}
                data-testid="advanced-diagnostics-json"
                aria-label="系统诊断JSON"
              />
              <p className="hint">含 FastAPI / SQLite / Python 等原始状态。</p>
              <button type="button" onClick={() => navigator.clipboard?.writeText(diagText)}>
                复制脱敏报告
              </button>
            </>
          )}
        </section>
      </article>
    </div>
  );
}
