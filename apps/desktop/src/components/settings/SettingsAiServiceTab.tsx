import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  DEFAULT_AI_SERVICE_ID,
  buildAiServiceViewModel,
} from "../../services/aiServiceViewModel";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  readStoredAnalysisMode,
  type AnalysisModePresetId,
  writeStoredAnalysisMode,
} from "../../services/analysisModePresets";
import {
  saveAiServiceConfiguration,
  testAiServiceConnection,
} from "../../services/aiServiceConfig";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import { useAdvancedSettingsStore } from "../../stores/advancedSettingsStore";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import { Loading } from "../common/States";

type Props = {
  autoOpenWizard?: boolean;
  focusField?: "api_key";
};

export function SettingsAiServiceTab({ autoOpenWizard = false, focusField }: Props) {
  const qc = useQueryClient();
  const showAdvanced = useAdvancedSettingsStore((s) => s.showAdvancedSettings);
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(() =>
    readStoredAnalysisMode() === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : readStoredAnalysisMode(),
  );
  const [cloudBodyConsent, setCloudBodyConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [userMessage, setUserMessage] = useState("");
  const [rawDiagnostic, setRawDiagnostic] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testErrorCode, setTestErrorCode] = useState<string | null>(null);

  const providers = useQuery({ queryKey: ["providers"], queryFn: providersApi.list });
  const cloud = useQuery({ queryKey: ["cloud"], queryFn: settingsApi.cloud });
  const configuration = useQuery({
    queryKey: ["provider-config", DEFAULT_AI_SERVICE_ID],
    queryFn: () => providersApi.configuration(DEFAULT_AI_SERVICE_ID),
  });

  useEffect(() => {
    if (autoOpenWizard || focusField === "api_key") {
      document.querySelector<HTMLInputElement>('[data-testid="ai-api-key-input"]')?.focus();
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

  const onTest = async () => {
    if (busy) return;
    setBusy(true);
    setUserMessage("");
    setRawDiagnostic("");
    setTestErrorCode(null);
    const result = await testAiServiceConnection(DEFAULT_AI_SERVICE_ID, qc);
    setUserMessage(result.userMessage);
    setRawDiagnostic(result.rawDiagnostic || "");
    setTestErrorCode(result.testErrorCode || null);
    setBusy(false);
  };

  const onSave = async () => {
    if (busy) return;
    setBusy(true);
    setUserMessage("");
    setRawDiagnostic("");
    setTestErrorCode(null);
    const modeToSave =
      showAdvanced && analysisMode === "CUSTOM"
        ? ("CUSTOM" as const)
        : (analysisMode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : analysisMode);
    const result = await saveAiServiceConfiguration({
      providerId: DEFAULT_AI_SERVICE_ID,
      apiKey,
      analysisMode: modeToSave,
      cloudBodyConsent,
      qc,
    });
    setUserMessage(result.userMessage);
    setRawDiagnostic(result.rawDiagnostic || "");
    setTestErrorCode(result.testErrorCode || null);
    if (result.ok) {
      setApiKey("");
      writeStoredAnalysisMode(modeToSave);
    }
    setBusy(false);
  };

  const disconnect = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await providersApi.action(DEFAULT_AI_SERVICE_ID, "disconnect");
      const latest = await providersApi.configuration(DEFAULT_AI_SERVICE_ID);
      qc.setQueryData(["provider-config", DEFAULT_AI_SERVICE_ID], latest);
      setUserMessage("已断开 AI 服务连接。");
      setTestErrorCode(null);
    } catch (error: any) {
      setUserMessage(error?.message || "断开失败");
    } finally {
      setBusy(false);
    }
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
        <p>连接阿里云百炼完成章节分析。Endpoint 与模型 ID 将随分析模式自动配置。</p>
      </header>

      <div className="ai-status-card" data-testid="ai-service-status-card">
        <div className="ai-status-main">
          <div>
            <p className="eyebrow">连接状态</p>
            <span
              className={`ai-status-badge ${view.canStartAnalysis ? "ok" : "warn"}`}
              data-testid="ai-service-connection-status"
            >
              {view.userStatusLabel}
            </span>
          </div>
        </div>
      </div>

      <div className="settings-fields">
        <label className="settings-field">
          <span>AI 服务</span>
          <input readOnly value="阿里云百炼（推荐）" aria-label="AI 服务" data-testid="ai-service-name" />
        </label>

        <label className="settings-field">
          <span>分析模式</span>
          <select
            aria-label="分析模式"
            data-testid="analysis-mode-select"
            value={analysisMode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : analysisMode}
            onChange={(e) => setAnalysisMode(e.target.value as AnalysisModePresetId)}
          >
            {ordinaryModeOptions().map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
            {showAdvanced && <option value="CUSTOM">自定义（高级）</option>}
          </select>
        </label>

        <label className="settings-field">
          <span>API Key</span>
          <input
            type="password"
            autoComplete="new-password"
            value={apiKey}
            aria-label="API Key"
            data-testid="ai-api-key-input"
            placeholder={view.apiKeyConfigured ? "已配置；留空表示不修改" : "粘贴你的 API Key"}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <p className="hint" data-testid="ai-service-api-key-state">
          凭据状态：{view.apiKeyConfigured ? "已配置" : "未配置"}（界面不会显示完整 Key）
        </p>

        <label className="consent">
          <input
            type="checkbox"
            checked={cloudBodyConsent}
            data-testid="cloud-body-consent"
            onChange={(e) => setCloudBodyConsent(e.target.checked)}
          />
          我确认分析时可将所选章节正文发送至阿里云百炼，费用由我的阿里云账户承担。
        </label>
      </div>

      {userMessage && (
        <p role="status" data-testid="ai-service-message">
          {userMessage}
        </p>
      )}

      <div className="settings-actions">
        <button
          type="button"
          data-testid="ai-service-test"
          disabled={busy || (!view.apiKeyConfigured && !apiKey)}
          onClick={() => void onTest()}
        >
          {busy ? "测试中…" : "测试连接"}
        </button>
        <button
          type="button"
          className="primary"
          data-testid="ai-service-save"
          disabled={busy || (!apiKey && !view.apiKeyConfigured)}
          onClick={() => void onSave()}
        >
          {busy ? "保存中…" : "保存"}
        </button>
        {showAdvanced && (
          <button
            type="button"
            data-testid="ai-service-disconnect"
            disabled={busy || !view.apiKeyConfigured}
            onClick={() => void disconnect()}
          >
            断开连接
          </button>
        )}
      </div>

      <button
        type="button"
        className="linkish"
        data-testid="ai-service-diagnostics-toggle"
        onClick={() => setShowDiagnostics((v) => !v)}
      >
        {showDiagnostics ? "收起详情" : "查看详情"}
      </button>
      {showDiagnostics && (
        <pre className="ai-diagnostics" data-testid="ai-service-diagnostics">
          {JSON.stringify(view.diagnostics, null, 2)}
          {rawDiagnostic ? `\n\n${rawDiagnostic}` : ""}
        </pre>
      )}

      {(developerMode || showAdvanced) && (
        <p className="hint">
          需要自定义 Endpoint 或 Model ID？请打开{" "}
          <Link to="/settings?tab=advanced">高级设置</Link>
          {developerMode && (
            <>
              {" "}
              或 <Link to="/providers">模型与 API</Link>
            </>
          )}
          。
        </p>
      )}
    </article>
  );
}
