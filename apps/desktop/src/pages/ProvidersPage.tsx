import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { providersApi } from "../services/providersApi";
import { Badge, ErrorState, Loading } from "../components/common/States";
import { AliyunForm } from "../components/providers/AliyunForm";
import { DeepSeekForm } from "../components/providers/DeepSeekForm";
import {
  cloudStateLabel,
  formatUnknown,
  healthStateLabel,
  providerDisplayName,
  providerListStatusLabel,
} from "../components/providers/providerDisplayLabels";
import { settingsApi } from "../services/settingsApi";
import { Link } from "react-router-dom";
import "../components/providers/providers.css";

type TransportStatus = "idle" | "running" | "succeeded" | "failed";
type RealTestStatus =
  | "idle"
  | "awaiting_confirmation"
  | "checking_budget"
  | "running"
  | "succeeded"
  | "failed";

type UiError = {
  code: string;
  message: string;
  status?: number;
  requestId?: string;
  retryable?: boolean;
  userActionHint?: string;
};

const TRANSPORT_LABELS: Record<string, string> = {
  PROVIDER_DNS_ERROR: "DNS解析失败",
  PROVIDER_CONNECT_TIMEOUT: "连接超时",
  PROVIDER_CONNECTION_ERROR: "连接失败",
  PROVIDER_TLS_ERROR: "TLS/证书失败",
  PROVIDER_PROXY_ERROR: "代理错误",
  PROVIDER_READ_TIMEOUT: "读取超时",
  PROVIDER_PROTOCOL_ERROR: "协议错误",
  PROVIDER_HTTP_ERROR: "HTTP错误",
  PROVIDER_DISABLED: "Provider已停用",
};

const CONNECTION_ERROR_LABELS: Record<string, { message: string; hint: string }> = {
  CLOUD_CONSENT_REQUIRED: {
    message: "尚未确认本次云端测试。",
    hint: "请阅读收费说明后点击“确认并测试”。",
  },
  PAID_TEST_CONFIRMATION_REQUIRED: {
    message: "尚未确认本次收费测试。",
    hint: "请重新打开确认框并点击“确认并测试”。",
  },
  BUDGET_NOT_AVAILABLE: {
    message: "当前无法计算本次分析费用",
    hint: "检查模型映射和计价配置，或切换到已有计价信息的模型。",
  },
  MODEL_PRICING_NOT_FOUND: {
    message: "当前模型缺少计价信息",
    hint: "检查模型映射和计价配置，或切换到已有计价信息的模型。",
  },
  INSUFFICIENT_BUDGET_RESERVATION: {
    message: "当前预算不足，无法开始分析",
    hint: "提高每日预算，或等待今日用量重置后再试。",
  },
  PROVIDER_DISABLED: {
    message: "Provider已停用。",
    hint: "请启用当前Provider。",
  },
  PROVIDER_NOT_CONFIGURED: {
    message: "Provider配置不完整。",
    hint: "请保存Base URL与模型配置后再试。",
  },
  PROVIDER_NOT_CONNECTED: {
    message: "Provider尚未连接。",
    hint: "请保存配置并连接后再试。",
  },
  CREDENTIAL_MISSING: {
    message: "未找到Provider凭据。",
    hint: "请重新保存API Key并连接Provider。",
  },
  CLOUD_MASTER_SWITCH_OFF: {
    message: "云端总开关已关闭。",
    hint: "请先开启“允许云端模型连接”。",
  },
  PROVIDER_CONNECTION_ERROR: {
    message: "无法连接云端Provider。",
    hint: "请先运行传输诊断并检查网络。",
  },
  PROVIDER_CONNECT_TIMEOUT: {
    message: "连接云端Provider超时。",
    hint: "请检查网络、代理或稍后重试。",
  },
  PROVIDER_READ_TIMEOUT: {
    message: "读取云端响应超时。",
    hint: "可稍后重试；持续发生时检查超时配置。",
  },
  PROVIDER_TLS_ERROR: {
    message: "TLS握手或证书校验失败。",
    hint: "请检查系统时间、代理和CA证书。",
  },
  AUTHENTICATION_FAILED: {
    message: "云端身份认证失败。",
    hint: "请重新检查API Key。",
  },
  PROVIDER_AUTHENTICATION_FAILED: {
    message: "云端身份认证失败。",
    hint: "请重新检查API Key。",
  },
  MODEL_NOT_FOUND: {
    message: "配置的模型不存在。",
    hint: "请核对Plus模型名称。",
  },
  PROVIDER_MODEL_NOT_FOUND: {
    message: "配置的模型不存在。",
    hint: "请核对Plus模型名称。",
  },
  REQUEST_VALIDATION_ERROR: {
    message: "请求或最小JSON响应校验失败。",
    hint: "请刷新页面后重试；持续失败时查看Invocation。",
  },
};

function normalizeConnectionError(error: any): UiError {
  const localized = CONNECTION_ERROR_LABELS[error?.code];
  return {
    code: error?.code || "CONNECTION_TEST_FAILED",
    message: localized?.message || error?.message || "真实连接测试失败。",
    status: error?.status,
    requestId: error?.requestId,
    retryable: error?.retryable,
    userActionHint:
      localized?.hint || error?.userActionHint || "请查看传输诊断和Provider配置。",
  };
}

export function ProvidersPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState("aliyun_qwen_plus");
  const [transportStatus, setTransportStatus] = useState<TransportStatus>("idle");
  const [transportResult, setTransportResult] = useState<any>();
  const [transportError, setTransportError] = useState("");
  const [realTestStatus, setRealTestStatus] = useState<RealTestStatus>("idle");
  const [realTestPreflight, setRealTestPreflight] = useState<any>();
  const [realTestResult, setRealTestResult] = useState<any>();
  const [realTestError, setRealTestError] = useState<UiError>();
  const providers = useQuery({
    queryKey: ["providers"],
    queryFn: providersApi.list,
  });
  const cloud = useQuery({ queryKey: ["cloud"], queryFn: providersApi.cloud });
  const configProfile = useQuery({
    queryKey: ["config-profile"],
    queryFn: settingsApi.configProfile,
  });
  const budget = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const usage = useQuery({ queryKey: ["cloud-usage"], queryFn: settingsApi.cloudUsage });
  const pricing = useQuery({ queryKey: ["cloud-pricing"], queryFn: settingsApi.cloudPricing });
  const routing = useQuery({
    queryKey: ["routing"],
    queryFn: providersApi.routing,
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["providers"] });
    qc.invalidateQueries({ queryKey: ["cloud"] });
    qc.invalidateQueries({ queryKey: ["cloud-usage"] });
    qc.invalidateQueries({ queryKey: ["cloud-pricing"] });
    qc.invalidateQueries({ queryKey: ["config-profile"] });
  };
  const blockedReasons = usage.data?.blocked_reasons ?? ["预算状态正在加载"];
  const runTransportDiagnostic = async () => {
    if (transportStatus === "running") return;
    setTransportStatus("running");
    setTransportError("");
    try {
      setTransportResult(await providersApi.transportDiagnostic(selected));
      setTransportStatus("succeeded");
    } catch (error: any) {
      setTransportResult(undefined);
      setTransportError(error?.message || "后端离线或传输诊断失败");
      setTransportStatus("failed");
    }
  };
  const openPaidTestConfirmation = async () => {
    if (realTestStatus === "checking_budget" || realTestStatus === "running") return;
    setRealTestStatus("awaiting_confirmation");
    setRealTestResult(undefined);
    setRealTestError(undefined);
    setRealTestPreflight(undefined);
    try {
      setRealTestPreflight(await providersApi.connectionTestPreflight(selected));
    } catch (error: any) {
      setRealTestError(normalizeConnectionError(error));
    }
  };
  const cancelPaidTest = () => {
    if (realTestStatus === "checking_budget" || realTestStatus === "running") return;
    setRealTestStatus("idle");
    setRealTestPreflight(undefined);
    setRealTestError(undefined);
  };
  const confirmPaidTest = async () => {
    if (realTestStatus !== "awaiting_confirmation") return;
    setRealTestStatus("checking_budget");
    setRealTestError(undefined);
    try {
      const [preflight] = await Promise.all([
        providersApi.connectionTestPreflight(selected),
        new Promise((resolve) => window.setTimeout(resolve, 120)),
      ]);
      setRealTestPreflight(preflight);
      if (!preflight.within_budget) {
        setRealTestStatus("failed");
        setRealTestError({
          code: preflight.blockers?.[0] || "BUDGET_NOT_AVAILABLE",
          message: "Provider或预算门禁未通过。",
          retryable: false,
          userActionHint: "请修复配置或预算后重新打开确认框。",
        });
        return;
      }
      setRealTestStatus("running");
      const result = await providersApi.testConnection(
        selected,
        preflight.max_output_tokens || 32,
      );
      setRealTestResult(result);
      setRealTestStatus("succeeded");
      refresh();
    } catch (error: any) {
      setRealTestError(normalizeConnectionError(error));
      setRealTestStatus("failed");
    }
  };
  const localAction = async (action: "start" | "stop") => {
    if (
      action === "start" &&
      !confirm("启动本地模型可能造成较高GPU负载，确认使用safe配置？")
    )
      return;
    if (action === "start") await providersApi.startLocal("safe");
    else await providersApi.stopLocal();
    refresh();
  };
  const selectedProvider = providers.data?.find((p) => p.name === selected);
  // Prefer list `enabled` (from ProviderConfiguration) over registry capabilities.enabled.
  const providerEnabled = Boolean(
    selectedProvider?.enabled ??
      (selectedProvider?.capabilities?.enabled === true ? true : false),
  );
  const cloudHydrated = !cloud.isLoading && cloud.data != null;
  const cloudEnabled = cloudHydrated ? Boolean(cloud.data?.enabled) : null;
  const realTestBusy =
    realTestStatus === "checking_budget" || realTestStatus === "running";
  const realTestButtonText = realTestBusy ? "测试中……" : "真实连接测试";
  const selectedDisplay = providerDisplayName(selected);
  const profile = configProfile.data;

  return (
    <section className="page providers-page" data-testid="providers-page">
      <div className="page-title">
        <div>
          <p className="eyebrow">连接与路由</p>
          <h1>模型与 API</h1>
          <p>前端只连接 FastAPI；不会直接调用任何云端服务。</p>
        </div>
      </div>
      {profile && (
        <div className="notice" role="status" data-testid="providers-config-environment-banner">
          <b>
            {profile.runtime_mode === "browser_dev"
              ? "当前为浏览器开发模式"
              : profile.runtime_mode === "desktop_dev"
                ? "当前为桌面开发模式"
                : "当前为正式安装版"}
          </b>
          <p>{profile.user_message}</p>
        </div>
      )}
      {providers.isLoading && <Loading />}
      {providers.error && <ErrorState error={providers.error} />}

      <section className="providers-section cloud-protection-summary panel" data-testid="cloud-protection-section">
        <header>
          <div>
            <p className="eyebrow">云端请求保护</p>
            <h2>预算与价格门禁</h2>
          </div>
          <Badge tone={blockedReasons.length ? "warning" : "success"}>
            {blockedReasons.length ? "已阻止收费请求" : "可用"}
          </Badge>
        </header>
        <div className="health-grid providers-health-grid">
          <span>
            云端总开关{" "}
            <b>
              {!cloudHydrated ? "加载中…" : cloudEnabled ? "开启" : "关闭"}
            </b>
          </span>
          <span>
            预算保护 <b>{budget.data?.cloud_request_budget_enabled ? "开启" : "关闭"}</b>
          </span>
          <span>
            每日费用上限{" "}
            <b>
              {formatUnknown(budget.data?.cloud_daily_estimated_cost_limit, " CNY")}
            </b>
          </span>
          <span>
            今日估算费用{" "}
            <b>
              {usage.data == null
                ? "—"
                : formatUnknown(usage.data.estimated_cost, " CNY")}
            </b>
          </span>
          <span>
            今日 Token{" "}
            <b>{usage.data == null ? "—" : formatUnknown(usage.data.total_tokens)}</b>
          </span>
          <span>
            剩余预算{" "}
            <b>{formatUnknown(usage.data?.remaining_estimated_cost, " CNY")}</b>
          </span>
          <span>
            价格配置{" "}
            <b>
              {pricing.data?.enabled
                ? "已配置"
                : pricing.data?.valid
                  ? "未验证"
                  : "无效或未配置"}
            </b>
          </span>
        </div>
        {blockedReasons.length > 0 && (
          <p role="alert">禁用原因：{blockedReasons.join("；")}</p>
        )}
        <div className="master-actions">
          <Link className="button" to="/settings">
            打开预算设置
          </Link>
          <button type="button" onClick={refresh}>
            刷新用量
          </button>
          <button type="button" onClick={() => providersApi.setCloud(false).then(refresh)}>
            关闭云端连接
          </button>
        </div>
      </section>

      <section className="providers-section cloud-master panel" data-testid="cloud-master-section">
        <div>
          <Badge tone={cloudEnabled ? "success" : "neutral"}>
            {!cloudHydrated ? "加载中" : cloudStateLabel(cloud.data?.state)}
          </Badge>
          <h2>允许云端模型连接</h2>
          <p className="providers-section-hint">
            关闭后禁止新云端请求，保留配置、凭据和历史记录。以后端 SQLite 为唯一事实源。
          </p>
        </div>
        <label className="switch">
          <input
            type="checkbox"
            data-testid="cloud-master-switch"
            checked={cloudEnabled === true}
            disabled={!cloudHydrated}
            onChange={(e) =>
              providersApi
                .setCloud(e.target.checked)
                .then(() => qc.invalidateQueries({ queryKey: ["cloud"] }))
            }
          />
          <span />
        </label>
        <div className="master-actions">
          <button
            type="button"
            onClick={() =>
              providers.data
                ?.filter((p) => p.capabilities.cloud)
                .forEach((p) => providersApi.action(p.name, "disconnect"))
            }
          >
            断开全部云端连接
          </button>
          <button
            type="button"
            className="danger"
            onClick={() =>
              confirm("确认删除全部云端凭据？") &&
              providers.data
                ?.filter((p) => p.capabilities.cloud)
                .forEach((p) => providersApi.deleteCredentials(p.name))
            }
          >
            删除全部云端凭据
          </button>
        </div>
      </section>

      <div className="provider-layout providers-layout">
        <aside className="provider-list providers-list providers-section" data-testid="provider-list-section">
          <header>
            <div>
              <p className="eyebrow">服务</p>
              <h3>Provider</h3>
            </div>
          </header>
          {providers.data?.map((p) => {
            const status = providerListStatusLabel(p);
            return (
              <button
                key={p.name}
                type="button"
                className={selected === p.name ? "selected" : ""}
                onClick={() => {
                  setSelected(p.name);
                  setTransportStatus("idle");
                  setTransportResult(undefined);
                  setTransportError("");
                  setRealTestStatus("idle");
                  setRealTestPreflight(undefined);
                  setRealTestResult(undefined);
                  setRealTestError(undefined);
                }}
              >
                <span>
                  <b>{providerDisplayName(p.name)}</b>
                  <small className="providers-tech-id" title={p.name}>
                    {p.name}
                  </small>
                  <small className="providers-tech-id" title={p.default_model}>
                    {p.default_model}
                  </small>
                </span>
                <Badge tone={status.tone}>{status.label}</Badge>
              </button>
            );
          })}
          {!providers.data?.some((p) => p.name === "deepseek") && (
            <button
              type="button"
              className={selected === "deepseek" ? "selected" : ""}
              onClick={() => {
                setSelected("deepseek");
                setTransportStatus("idle");
                setTransportResult(undefined);
                setTransportError("");
                setRealTestStatus("idle");
                setRealTestPreflight(undefined);
                setRealTestResult(undefined);
                setRealTestError(undefined);
              }}
            >
              <span>
                <b>深度求索/DeepSeek</b>
                <small className="providers-tech-id" title="deepseek">
                  deepseek
                </small>
              </span>
              <Badge>可配置</Badge>
            </button>
          )}
          {["智谱 GLM", "Kimi"].map((p) => (
            <button type="button" disabled key={p}>
              <span>
                <b>{p}</b>
                <small>后续支持</small>
              </span>
              <Badge>规划中</Badge>
            </button>
          ))}
        </aside>

        <article className="panel config-panel providers-section providers-config-panel">
          <header>
            <div>
              <p className="eyebrow">当前配置</p>
              <h2>{selectedDisplay}</h2>
              <code className="providers-tech-id">{selected}</code>
            </div>
            <Badge>
              {providers.data?.find((p) => p.name === selected)?.capabilities.region ||
                "local"}
            </Badge>
          </header>
          {selected === "deepseek" ? (
            <>
              <div className="notice">
                <b>能力状态</b>
                <span>OpenAI 兼容 · Thinking 默认关闭 · Flash/Pro 可选</span>
                <span>与阿里云百炼密钥相互独立</span>
              </div>
              <DeepSeekForm onSaved={refresh} />
            </>
          ) : selected.startsWith("aliyun_") ? (
            <>
              {selected === "aliyun_qwen_plus" && (
                <div className="notice">
                  <b>能力状态</b>
                  <span>结构化输出通过 · Scene Analysis通过 · 场景边界需人工确认</span>
                  <span>不参与全自动路由</span>
                </div>
              )}
              <div className="panel" data-testid="transport-diagnostic-panel">
                <header>
                  <div>
                    <p className="eyebrow">连通性</p>
                    <h3>传输诊断</h3>
                    <p>传输诊断不会调用模型，不消耗Token。</p>
                  </div>
                  <Badge tone={providerEnabled ? "success" : "neutral"}>
                    {providerEnabled ? "已启用" : "已停用"}
                  </Badge>
                </header>
                <div className="master-actions">
                  <button
                    type="button"
                    data-testid="transport-diagnostic-button"
                    disabled={transportStatus === "running"}
                    onClick={runTransportDiagnostic}
                  >
                    {transportStatus === "running" ? "诊断中……" : "传输诊断"}
                  </button>
                  <button
                    type="button"
                    data-testid="paid-connection-test-button"
                    disabled={realTestBusy}
                    title="将先显示收费确认，不会立即调用模型。"
                    onClick={openPaidTestConfirmation}
                  >
                    {realTestButtonText}
                  </button>
                </div>
                <p className="notice">
                  真实连接测试将发送原创最小请求，可能产生少量Token费用。
                </p>
                {transportError && (
                  <p role="alert" data-testid="transport-diagnostic-error">
                    {transportError}
                  </p>
                )}
                {transportResult && (
                  <div data-testid="transport-diagnostic-result">
                    <h4>传输诊断结果</h4>
                    <dl className="providers-diag-dl">
                      <dt>总体</dt>
                      <dd>
                        {transportResult.overall_status}
                        {transportResult.error_code
                          ? ` · ${TRANSPORT_LABELS[transportResult.error_code] || transportResult.error_code}`
                          : ""}
                      </dd>
                      <dt>配置</dt>
                      <dd>{transportResult.configuration_valid ? "有效" : "无效"}</dd>
                      <dt>DNS</dt>
                      <dd>
                        {transportResult.dns?.status}
                        {transportResult.dns?.latency_ms != null
                          ? ` · ${transportResult.dns.latency_ms}ms`
                          : ""}
                      </dd>
                      <dt>TCP</dt>
                      <dd>
                        {transportResult.tcp?.status}
                        {transportResult.tcp?.latency_ms != null
                          ? ` · ${transportResult.tcp.latency_ms}ms`
                          : ""}
                      </dd>
                      <dt>TLS</dt>
                      <dd>
                        {transportResult.tls?.status}
                        {transportResult.tls?.certificate_valid === true ? " · 证书有效" : ""}
                        {transportResult.tls?.latency_ms != null
                          ? ` · ${transportResult.tls.latency_ms}ms`
                          : ""}
                      </dd>
                      <dt>Proxy</dt>
                      <dd>
                        {transportResult.proxy?.detected
                          ? `检测到（${transportResult.proxy.source}）`
                          : "未检测到"}
                      </dd>
                      <dt>CA证书</dt>
                      <dd>
                        {transportResult.ca_bundle?.status} ·{" "}
                        {transportResult.ca_bundle?.source}
                      </dd>
                      <dt>Endpoint形态</dt>
                      <dd>
                        {transportResult.request_endpoint_shape?.status} ·{" "}
                        <code className="providers-tech-id">
                          {transportResult.request_endpoint_shape?.path_redacted}
                        </code>
                      </dd>
                      <dt>建议</dt>
                      <dd>{transportResult.user_action_hint || "无"}</dd>
                    </dl>
                  </div>
                )}
                {realTestStatus === "checking_budget" && (
                  <p role="status">正在检查Provider和预算……</p>
                )}
                {realTestStatus === "running" && (
                  <p role="status">正在发送原创最小测试请求……</p>
                )}
                {realTestError && (
                  <div role="alert" data-testid="real-connection-test-error">
                    <h4>真实连接测试结果：失败</h4>
                    <p>{realTestError.message}</p>
                    <p>
                      错误代码：
                      <code className="providers-tech-id">{realTestError.code}</code>
                    </p>
                    <p>HTTP：{realTestError.status ?? "无响应"}</p>
                    <p>
                      request_id：
                      <code className="providers-tech-id">
                        {realTestError.requestId || "无"}
                      </code>
                    </p>
                    <p>是否可重试：{realTestError.retryable ? "是" : "否"}</p>
                    <p>处理建议：{realTestError.userActionHint}</p>
                  </div>
                )}
                {realTestResult && (
                  <div data-testid="real-connection-test-result">
                    <h4>真实连接测试结果：成功</h4>
                    <dl className="providers-diag-dl">
                      <dt>HTTP</dt>
                      <dd>{realTestResult.http_status}</dd>
                      <dt>Provider</dt>
                      <dd>
                        <code className="providers-tech-id">{realTestResult.provider}</code>
                      </dd>
                      <dt>配置模型</dt>
                      <dd>
                        <code className="providers-tech-id">
                          {realTestResult.configured_model}
                        </code>
                      </dd>
                      <dt>响应模型</dt>
                      <dd>
                        <code className="providers-tech-id">
                          {realTestResult.response_model}
                        </code>
                      </dd>
                      <dt>JSON</dt>
                      <dd>{realTestResult.json_valid ? "通过" : "失败"}</dd>
                      <dt>Schema</dt>
                      <dd>{realTestResult.schema_valid ? "通过" : "失败"}</dd>
                      <dt>输入Token</dt>
                      <dd>{realTestResult.input_tokens ?? "未知"}</dd>
                      <dt>输出Token</dt>
                      <dd>{realTestResult.output_tokens ?? "未知"}</dd>
                      <dt>总Token</dt>
                      <dd>{realTestResult.total_tokens ?? "未知"}</dd>
                      <dt>耗时</dt>
                      <dd>{realTestResult.latency_ms} ms</dd>
                      <dt>Invocation</dt>
                      <dd>#{realTestResult.invocation_id}</dd>
                      <dt>request_id</dt>
                      <dd>
                        <code className="providers-tech-id">
                          {realTestResult.request_id || "无"}
                        </code>
                      </dd>
                      <dt>估算费用</dt>
                      <dd>
                        {realTestResult.estimated_cost ?? "未知"}{" "}
                        {realTestResult.currency || ""}
                      </dd>
                      <dt>价格版本</dt>
                      <dd>{realTestResult.pricing_version || "未知"}</dd>
                    </dl>
                  </div>
                )}
              </div>
              <AliyunForm provider={selected} onSaved={refresh} />
            </>
          ) : (
            <div className="local-config">
              <h3>本地 Provider</h3>
              <p>本地模型路径和运行参数由受保护的本机 Profile 管理。</p>
              <div className="master-actions">
                <button type="button" onClick={() => localAction("start")}>
                  启动本地服务
                </button>
                <button type="button" onClick={() => localAction("stop")}>
                  停止本地服务
                </button>
                <button type="button" onClick={refresh}>
                  刷新状态
                </button>
              </div>
              <dl className="providers-diag-dl">
                <dt>模型</dt>
                <dd>
                  <code className="providers-tech-id">
                    {providers.data?.find((p) => p.name === selected)?.default_model}
                  </code>
                </dd>
                <dt>自动路由</dt>
                <dd>
                  {providers.data?.find((p) => p.name === selected)?.capabilities
                    .manual_only
                    ? "不允许（manual-only）"
                    : "候选"}
                </dd>
                <dt>连接</dt>
                <dd>
                  {providers.data?.find((p) => p.name === selected)?.connected
                    ? "已连接"
                    : "未连接"}
                </dd>
                <dt>健康</dt>
                <dd>
                  {healthStateLabel(
                    providers.data?.find((p) => p.name === selected)?.health_state,
                    providers.data?.find((p) => p.name === selected)?.healthy,
                  )}
                </dd>
              </dl>
            </div>
          )}
        </article>

        <aside className="panel routing providers-section providers-routing" data-testid="routing-preview-section">
          <header>
            <div>
              <p className="eyebrow">任务分配</p>
              <h2>路由预览</h2>
            </div>
          </header>
          {routing.data?.map((r) => (
            <div key={r.task} className="providers-routing-row">
              <b>{r.task}</b>
              <span>
                →{" "}
                <code className="providers-tech-id">
                  {r.provider}
                </code>
                {r.model ? (
                  <>
                    {" "}
                    /{" "}
                    <code className="providers-tech-id">{r.model}</code>
                  </>
                ) : null}
              </span>
              <small>
                {r.available ? "可用" : "不可选"} ·{" "}
                {r.sends_content_to_cloud ? "发送正文到云端" : "本地处理"}
              </small>
            </div>
          ))}
        </aside>
      </div>

      {realTestStatus === "awaiting_confirmation" && (
        <div className="modal-backdrop" data-testid="connection-test-confirmation">
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="connection-test-title"
          >
            <header>
              <h2 id="connection-test-title">执行真实连接测试</h2>
              <button type="button" aria-label="关闭" onClick={cancelPaidTest}>
                ×
              </button>
            </header>
            <p>
              本测试将向云端模型发送一条原创最小JSON请求，不会发送小说正文，
              可能产生少量Token费用。
            </p>
            <dl className="providers-diag-dl">
              <dt>Provider</dt>
              <dd>
                {selectedDisplay}{" "}
                <code className="providers-tech-id">{selected}</code>
              </dd>
              <dt>模型</dt>
              <dd>
                <code className="providers-tech-id">
                  {realTestPreflight?.configured_model ||
                    selectedProvider?.default_model ||
                    "加载中……"}
                </code>
              </dd>
              <dt>最大输出Token</dt>
              <dd>{realTestPreflight?.max_output_tokens ?? 32}</dd>
              <dt>最大真实请求</dt>
              <dd>1</dd>
              <dt>预计费用</dt>
              <dd>
                {realTestPreflight
                  ? realTestPreflight.estimated_cost == null
                    ? "无法计算（缺少计价信息）"
                    : `${realTestPreflight.estimated_cost} ${realTestPreflight.currency || ""}`
                  : "正在读取预算……"}
              </dd>
              <dt>当前剩余预算</dt>
              <dd>
                {realTestPreflight
                  ? `${realTestPreflight.remaining_requests} 请求 / ${realTestPreflight.remaining_tokens} Token / ${realTestPreflight.remaining_estimated_cost} ${realTestPreflight.currency || ""}`
                  : "正在读取……"}
              </dd>
              <dt>用户内容</dt>
              <dd>不发送用户小说正文</dd>
              <dt>模型服务验证</dt>
              <dd data-testid="connection-test-model-status">
                {realTestPreflight
                  ? realTestPreflight.blockers?.some((b: string) =>
                      /CREDENTIAL|PROVIDER_DISABLED|PROVIDER_NOT|CLOUD_MASTER|AUTH/i.test(b),
                    )
                    ? "未通过"
                    : realTestPreflight.blockers?.some((b: string) =>
                          /BUDGET_NOT_AVAILABLE|MODEL_PRICING|INSUFFICIENT_BUDGET/i.test(b),
                        )
                      ? "可尝试（分析配置未就绪）"
                      : "可执行"
                  : "检查中…"}
              </dd>
              <dt>分析就绪检查</dt>
              <dd data-testid="connection-test-readiness-status">
                {realTestPreflight
                  ? realTestPreflight.within_budget
                    ? "已就绪"
                    : `未就绪：${(realTestPreflight.blockers || [])
                        .map((code: string) => CONNECTION_ERROR_LABELS[code]?.message || code)
                        .join("；")}`
                  : "检查中…"}
              </dd>
            </dl>
            {realTestPreflight && !realTestPreflight.within_budget && (
              <div role="alert" data-testid="connection-test-block-reason">
                <p>
                  当前不可测试：
                  {(realTestPreflight.blockers || [])
                    .map((code: string) => CONNECTION_ERROR_LABELS[code]?.message || code)
                    .join("、")}
                </p>
                <p>
                  {(realTestPreflight.blockers || [])
                    .map((code: string) => CONNECTION_ERROR_LABELS[code]?.hint)
                    .filter(Boolean)
                    .join(" ")}
                </p>
                <details>
                  <summary>技术详情</summary>
                  <pre>{(realTestPreflight.blockers || []).join(", ")}</pre>
                </details>
              </div>
            )}
            {realTestError && (
              <p role="alert">
                {realTestError.message} {realTestError.userActionHint}
              </p>
            )}
            <footer>
              <button type="button" onClick={cancelPaidTest}>
                取消
              </button>
              <button
                type="button"
                className="primary"
                disabled={
                  !realTestPreflight ||
                  !realTestPreflight.within_budget ||
                  Boolean(realTestError)
                }
                onClick={confirmPaidTest}
              >
                确认并测试
              </button>
            </footer>
          </div>
        </div>
      )}
    </section>
  );
}
