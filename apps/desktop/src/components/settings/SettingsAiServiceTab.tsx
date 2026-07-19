import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { settingsApi } from "../../services/settingsApi";
import { providersApi } from "../../services/providersApi";
import {
  DEFAULT_AI_SERVICE_ID,
  DEFAULT_AI_SERVICE_DISPLAY_NAME,
  DEFAULT_AI_MODEL,
  buildAiServiceViewModel,
  mapTransportOrHttpError,
  serviceDisplayNameFor,
} from "../../services/aiServiceViewModel";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import { Loading } from "../common/States";

const CATALOG = [
  {
    id: DEFAULT_AI_SERVICE_ID,
    name: "阿里云百炼 · Qwen",
    modelTier: "Qwen Plus（默认推荐）",
    model: DEFAULT_AI_MODEL,
  },
];

type WizardStep = 1 | 2 | 3 | 4;

type Props = {
  autoOpenWizard?: boolean;
  focusField?: "api_key";
};

export function SettingsAiServiceTab({ autoOpenWizard = false, focusField }: Props) {
  const qc = useQueryClient();
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [step, setStep] = useState<WizardStep>(1);
  const [selectedService, setSelectedService] = useState(DEFAULT_AI_SERVICE_ID);
  const [apiKey, setApiKey] = useState("");
  const [modelTier] = useState<"qwen_plus">("qwen_plus");
  const [dailyCostLimit, setDailyCostLimit] = useState("20");
  const [cloudBodyConsent, setCloudBodyConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [userMessage, setUserMessage] = useState("");
  const [rawDiagnostic, setRawDiagnostic] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testErrorCode, setTestErrorCode] = useState<string | null>(null);

  const providers = useQuery({ queryKey: ["providers"], queryFn: providersApi.list });
  const cloud = useQuery({ queryKey: ["cloud"], queryFn: settingsApi.cloud });
  const usage = useQuery({ queryKey: ["cloud-usage"], queryFn: settingsApi.cloudUsage });
  const budget = useQuery({ queryKey: ["cloud-budget"], queryFn: settingsApi.cloudBudget });
  const configuration = useQuery({
    queryKey: ["provider-config", DEFAULT_AI_SERVICE_ID],
    queryFn: () => providersApi.configuration(DEFAULT_AI_SERVICE_ID),
  });

  useEffect(() => {
    if (typeof budget.data?.cloud_daily_estimated_cost_limit === "number") {
      setDailyCostLimit(String(budget.data.cloud_daily_estimated_cost_limit));
    }
  }, [budget.data?.cloud_daily_estimated_cost_limit]);

  useEffect(() => {
    if (autoOpenWizard) {
      setWizardOpen(true);
      setStep(focusField === "api_key" ? 2 : 1);
    }
  }, [autoOpenWizard, focusField]);

  const provider = useMemo(
    () =>
      (providers.data || []).find((p) => p.name === DEFAULT_AI_SERVICE_ID) ||
      (providers.data || []).find((p) => p.capabilities?.cloud) ||
      null,
    [providers.data],
  );

  const view = useMemo(
    () =>
      buildAiServiceViewModel({
        provider,
        configuration: configuration.data,
        cloudEnabled: cloud.data?.enabled,
        connectionErrorCode: testErrorCode,
      }),
    [provider, configuration.data, cloud.data?.enabled, testErrorCode],
  );

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["providers"] }),
      qc.invalidateQueries({ queryKey: ["cloud"] }),
      qc.invalidateQueries({ queryKey: ["cloud-usage"] }),
      qc.invalidateQueries({ queryKey: ["provider-config"] }),
    ]);
  };

  /** Persist connect on backend, then refresh configuration (source of truth). */
  const persistConnected = async (providerId: string) => {
    if (!cloud.data?.enabled) {
      await settingsApi.setCloud(true);
    }
    await providersApi.action(providerId, "enable");
    await providersApi.action(providerId, "connect");
    const latest = await providersApi.configuration(providerId);
    qc.setQueryData(["provider-config", providerId], latest);
  };

  const openWizard = (reconfigure = false) => {
    setWizardOpen(true);
    setStep(reconfigure || view.apiKeyConfigured ? 2 : 1);
    setApiKey("");
    setCloudBodyConsent(false);
    setUserMessage("");
    setRawDiagnostic("");
    setTestErrorCode(null);
  };

  const saveAndTest = async () => {
    if (busy) return;
    if (!cloudBodyConsent) {
      setUserMessage("请先确认云端正文发送说明。");
      return;
    }
    setBusy(true);
    setUserMessage("");
    setRawDiagnostic("");
    setTestErrorCode(null);
    try {
      const existing = await providersApi.configuration(selectedService);
      const costLimit = Math.max(0.01, Number(dailyCostLimit) || 20);
      const currentBudget = await settingsApi.cloudBudget();
      await settingsApi.saveCloudBudget({
        ...currentBudget,
        cloud_daily_estimated_cost_limit: costLimit,
      });
      await providersApi.save(selectedService, {
        ...existing,
        display_name: serviceDisplayNameFor(selectedService) || DEFAULT_AI_SERVICE_DISPLAY_NAME,
        // Ordinary wizard locks Plus tier; engineering fields stay backend-default.
        plus_model: DEFAULT_AI_MODEL,
        api_key: apiKey || null,
        enabled: true,
        disconnected: false,
        allow_auto_route: false,
      });
      if (!cloud.data?.enabled) {
        await settingsApi.setCloud(true);
      }
      // Zero-cost connectivity check only (no model invocation).
      const transport = await providersApi.transportDiagnostic(selectedService);
      setRawDiagnostic(JSON.stringify(transport, null, 2));
      if (transport.overall_status === "ok" || transport.overall_status === "healthy") {
        await persistConnected(selectedService);
        setUserMessage("连接成功。可以开始分析。");
        setStep(4);
      } else {
        const mapped = mapTransportOrHttpError({
          code: transport.error_code || "TRANSPORT_FAILED",
          message: transport.user_action_hint || transport.overall_status,
        });
        setTestErrorCode(mapped.rawCode);
        setUserMessage(mapped.userLabel);
        setStep(4);
      }
    } catch (error: any) {
      const mapped = mapTransportOrHttpError(error);
      setTestErrorCode(mapped.rawCode);
      setUserMessage(mapped.userLabel);
      setRawDiagnostic(
        JSON.stringify(
          {
            code: error?.code,
            status: error?.status,
            message: error?.message,
            requestId: error?.requestId,
          },
          null,
          2,
        ),
      );
      setStep(4);
    } finally {
      setBusy(false);
    }
    // Background refresh must not keep the UI in "测试中…"
    void refresh();
  };

  const testConnection = async () => {
    if (busy) return;
    setBusy(true);
    setUserMessage("");
    setRawDiagnostic("");
    setTestErrorCode(null);
    try {
      const transport = await providersApi.transportDiagnostic(DEFAULT_AI_SERVICE_ID);
      setRawDiagnostic(JSON.stringify(transport, null, 2));
      if (transport.overall_status === "ok" || transport.overall_status === "healthy") {
        await persistConnected(DEFAULT_AI_SERVICE_ID);
        setTestErrorCode(null);
        setUserMessage("连接正常。");
      } else {
        const mapped = mapTransportOrHttpError({
          code: transport.error_code || "TRANSPORT_FAILED",
          message: transport.user_action_hint || transport.overall_status,
        });
        setTestErrorCode(mapped.rawCode);
        setUserMessage(mapped.userLabel);
      }
    } catch (error: any) {
      const mapped = mapTransportOrHttpError(error);
      setTestErrorCode(mapped.rawCode);
      setUserMessage(mapped.userLabel);
      setRawDiagnostic(
        JSON.stringify(
          { code: error?.code, status: error?.status, message: error?.message },
          null,
          2,
        ),
      );
    } finally {
      setBusy(false);
    }
    void refresh();
  };

  const disconnect = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await providersApi.action(DEFAULT_AI_SERVICE_ID, "disconnect");
      const latest = await providersApi.configuration(DEFAULT_AI_SERVICE_ID);
      qc.setQueryData(["provider-config", DEFAULT_AI_SERVICE_ID], latest);
      setUserMessage("已断开AI服务连接。");
      setTestErrorCode(null);
    } catch (error: any) {
      setUserMessage(error?.message || "断开失败");
    } finally {
      setBusy(false);
    }
    void refresh();
  };

  const deleteCredentials = async () => {
    if (busy) return;
    if (!window.confirm("确定删除本机保存的 API Key？删除后将无法继续调用云端，直至重新配置。")) {
      return;
    }
    setBusy(true);
    try {
      await providersApi.deleteCredentials(DEFAULT_AI_SERVICE_ID);
      await providersApi.action(DEFAULT_AI_SERVICE_ID, "disconnect");
      const latest = await providersApi.configuration(DEFAULT_AI_SERVICE_ID);
      qc.setQueryData(["provider-config", DEFAULT_AI_SERVICE_ID], latest);
      setUserMessage("凭据已删除。");
      setTestErrorCode(null);
    } catch (error: any) {
      setUserMessage(error?.message || "删除凭据失败");
    } finally {
      setBusy(false);
    }
    void refresh();
  };

  if (providers.isLoading || configuration.isLoading) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  return (
    <article className="settings-panel" data-testid="settings-panel-ai-service">
      <header className="settings-panel-header">
        <h2>AI 服务</h2>
        <p>配置云端分析服务。无需了解 Provider 或 API 路由。</p>
      </header>

      {!wizardOpen && (
        <div className="ai-status-card" data-testid="ai-service-status-card">
          <div className="ai-status-main">
            <div>
              <p className="eyebrow">当前AI服务</p>
              <h3 data-testid="ai-service-name">{view.serviceDisplayName}</h3>
              <p data-testid="ai-service-model">当前模型：{view.modelDisplayName}</p>
            </div>
            <span
              className={`ai-status-badge ${view.canStartAnalysis ? "ok" : "warn"}`}
              data-testid="ai-service-connection-status"
            >
              {view.userStatusLabel}
            </span>
          </div>
          <dl className="ai-status-meta">
            <div>
              <dt>API Key</dt>
              <dd data-testid="ai-service-api-key-state">
                {view.apiKeyConfigured ? "已配置" : "未配置"}
              </dd>
            </div>
            <div>
              <dt>今日费用</dt>
              <dd data-testid="ai-service-today-cost">
                {usage.data?.estimated_cost ?? 0} CNY
              </dd>
            </div>
          </dl>
          {userMessage && <p role="status">{userMessage}</p>}
          <div className="settings-actions">
            <button
              type="button"
              className="primary"
              data-testid="ai-service-configure"
              onClick={() => openWizard(view.apiKeyConfigured)}
            >
              {view.apiKeyConfigured ? "重新配置" : "配置"}
            </button>
            <button
              type="button"
              data-testid="ai-service-test"
              disabled={busy || !view.apiKeyConfigured}
              onClick={testConnection}
            >
              {busy ? "测试中…" : "测试连接"}
            </button>
            <button
              type="button"
              data-testid="ai-service-disconnect"
              disabled={busy || !view.apiKeyConfigured}
              onClick={disconnect}
            >
              断开连接
            </button>
            <button
              type="button"
              data-testid="ai-service-delete-credentials"
              disabled={busy || !view.apiKeyConfigured}
              onClick={deleteCredentials}
            >
              删除凭据
            </button>
          </div>
          <button
            type="button"
            className="linkish"
            data-testid="ai-service-diagnostics-toggle"
            onClick={() => setShowDiagnostics((v) => !v)}
          >
            {showDiagnostics ? "收起诊断详情" : "查看诊断详情"}
          </button>
          {showDiagnostics && (
            <pre className="ai-diagnostics" data-testid="ai-service-diagnostics">
              {JSON.stringify(view.diagnostics, null, 2)}
              {rawDiagnostic ? `\n\n${rawDiagnostic}` : ""}
            </pre>
          )}
        </div>
      )}

      {wizardOpen && (
        <div
          className="ai-setup-wizard"
          data-testid="ai-service-wizard"
          data-qwen-setup-wizard="1"
        >
          <ol className="wizard-steps" aria-label="配置步骤">
            <li className={step >= 1 ? "active" : ""}>选择服务与档位</li>
            <li className={step >= 2 ? "active" : ""}>API Key 与预算</li>
            <li className={step >= 3 ? "active" : ""}>确认并测试</li>
            <li className={step >= 4 ? "active" : ""}>结果</li>
          </ol>

          {step === 1 && (
            <div data-testid="wizard-step-1">
              <p>V1.0 普通模式正式支持：</p>
              <div className="service-catalog">
                {CATALOG.map((item) => (
                  <label key={item.id} className="service-option">
                    <input
                      type="radio"
                      name="ai-service"
                      checked={selectedService === item.id}
                      onChange={() => setSelectedService(item.id)}
                    />
                    <span>
                      <b>{item.name}</b>
                      <small>模型档位：{item.modelTier}</small>
                    </span>
                  </label>
                ))}
              </div>
              <label className="settings-field">
                <span>模型档位</span>
                <select
                  aria-label="模型档位"
                  value={modelTier}
                  disabled
                  data-testid="qwen-model-tier"
                >
                  <option value="qwen_plus">Qwen Plus（默认推荐）</option>
                </select>
              </label>
              <p className="hint">
                系统将自动使用推荐配置。普通界面不需要填写 Provider ID、Base URL 或路由参数。
              </p>
              <div className="settings-actions">
                <button type="button" onClick={() => setWizardOpen(false)}>
                  取消
                </button>
                <button
                  type="button"
                  className="primary"
                  onClick={() => setStep(2)}
                >
                  下一步
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div data-testid="wizard-step-2">
              <label className="settings-field">
                <span>API Key</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  aria-label="API Key"
                  data-testid="qwen-api-key-input"
                  autoFocus={focusField === "api_key"}
                  placeholder={
                    view.apiKeyConfigured ? "已配置；留空表示不修改" : "粘贴你的 API Key"
                  }
                  onChange={(e) => setApiKey(e.target.value)}
                />
              </label>
              <label className="settings-field">
                <span>每日费用上限（CNY）</span>
                <input
                  type="number"
                  min={0.01}
                  step={0.5}
                  value={dailyCostLimit}
                  aria-label="每日费用上限"
                  data-testid="qwen-daily-cost-limit"
                  onChange={(e) => setDailyCostLimit(e.target.value)}
                />
              </label>
              <p className="hint">
                密钥仅保存在操作系统凭据管理器，不会写入浏览器 LocalStorage、SQLite 明文、日志或导出文件。
                界面只显示「已配置 / 未配置」。
              </p>
              <div className="settings-actions">
                <button type="button" onClick={() => setStep(1)}>
                  上一步
                </button>
                <button
                  type="button"
                  className="primary"
                  disabled={!apiKey && !view.apiKeyConfigured}
                  onClick={() => setStep(3)}
                >
                  下一步
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div data-testid="wizard-step-3">
              <label className="consent">
                <input
                  type="checkbox"
                  checked={cloudBodyConsent}
                  data-testid="qwen-cloud-body-consent"
                  onChange={(e) => setCloudBodyConsent(e.target.checked)}
                />
                我确认分析时可将所选章节正文发送至阿里云百炼 · Qwen，费用由我的阿里云账户承担。
              </label>
              <p>
                将保存配置并检测网络连通性（不调用模型、不产生 Token 费用）。页面加载不会自动测试连接。
              </p>
              <div className="settings-actions">
                <button type="button" disabled={busy} onClick={() => setStep(2)}>
                  上一步
                </button>
                <button
                  type="button"
                  className="primary"
                  disabled={busy || !cloudBodyConsent}
                  data-testid="wizard-save-test"
                  onClick={saveAndTest}
                >
                  {busy ? "保存并测试中…" : "保存并测试连接"}
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div data-testid="wizard-step-4">
              <p role="status" data-testid="wizard-result">
                {userMessage || "已完成"}
              </p>
              <button
                type="button"
                className="linkish"
                onClick={() => setShowDiagnostics((v) => !v)}
              >
                {showDiagnostics ? "收起诊断详情" : "查看诊断详情"}
              </button>
              {showDiagnostics && (
                <pre className="ai-diagnostics" data-testid="wizard-diagnostics">
                  {rawDiagnostic || JSON.stringify(view.diagnostics, null, 2)}
                </pre>
              )}
              <div className="settings-actions">
                <button
                  type="button"
                  className="primary"
                  onClick={() => {
                    setWizardOpen(false);
                    setStep(1);
                  }}
                >
                  完成
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {developerMode && (
        <p className="hint">
          开发者模式已开启：可在「高级设置」查看 Provider、路由与传输诊断，或打开{" "}
          <Link to="/providers">模型与API</Link>。
        </p>
      )}
    </article>
  );
}
