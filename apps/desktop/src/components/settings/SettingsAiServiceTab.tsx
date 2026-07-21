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
  configureRecommendedQwenService,
  fetchRecommendedQwenStatus,
  repairRecommendedQwenSetup,
} from "../../services/aiServiceConfig";
import { formatSetupErrorBlock, mapSetupError, stripRawErrorCodes } from "../../services/setupErrorCopy";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import { useAdvancedSettingsStore } from "../../stores/advancedSettingsStore";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import { Loading } from "../common/States";
import "./settings.css";

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
  const [busy, setBusy] = useState<"verify" | "save" | "repair" | "disconnect" | null>(null);
  const [userMessage, setUserMessage] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testErrorCode, setTestErrorCode] = useState<string | null>(null);
  const [modelValidated, setModelValidated] = useState(false);

  const setup = useQuery({
    queryKey: ["recommended-qwen-setup"],
    queryFn: fetchRecommendedQwenStatus,
    refetchOnMount: "always",
    staleTime: 0,
  });
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

  useEffect(() => {
    if (
      setup.data?.analysis_mode === "FAST" ||
      setup.data?.analysis_mode === "BALANCED" ||
      setup.data?.analysis_mode === "QUALITY"
    ) {
      setAnalysisMode(setup.data.analysis_mode);
    }
  }, [setup.data?.analysis_mode]);

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
        cloudEnabled: setup.data?.cloud_enabled ?? cloud.data?.enabled,
        providerEligible: setup.data?.provider_eligible ?? provider?.manual_boundary_candidate_eligible,
        connectionErrorCode: testErrorCode,
      }),
    [
      provider,
      configuration.data,
      cloud.data?.enabled,
      setup.data?.cloud_enabled,
      setup.data?.provider_eligible,
      testErrorCode,
    ],
  );

  const eligible = setup.data?.provider_eligible === true || setup.data?.analysis_ready === true;
  const primaryBlocker = (setup.data?.blockers || view.diagnostics.blockers || [])[0];
  const readinessLabel = eligible
    ? "当前可用于分析"
    : primaryBlocker
      ? `当前不可用于分析\n原因：${mapSetupError(primaryBlocker, { model: view.modelDisplayName }).title}`
      : "当前不可用于分析";

  const modeToSave = (
    showAdvanced && analysisMode === "CUSTOM"
      ? DEFAULT_ANALYSIS_MODE
      : analysisMode === "CUSTOM"
        ? DEFAULT_ANALYSIS_MODE
        : analysisMode
  ) as "FAST" | "BALANCED" | "QUALITY";

  const onVerify = async () => {
    if (busy) return;
    setBusy("verify");
    setUserMessage("");
    setTestErrorCode(null);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: modeToSave,
      cloudBodyConsent,
      persist: false,
      qc,
    });
    setUserMessage(stripRawErrorCodes(result.user_message));
    setTestErrorCode(result.error_code || null);
    setModelValidated(Boolean(result.model_service_validated ?? result.model_validated ?? result.ok));
    setBusy(null);
  };

  const onSave = async () => {
    if (busy) return;
    setBusy("save");
    setUserMessage("");
    setTestErrorCode(null);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: modeToSave,
      cloudBodyConsent,
      persist: true,
      qc,
    });
    setUserMessage(stripRawErrorCodes(result.user_message));
    setTestErrorCode(result.error_code || null);
    setModelValidated(Boolean(result.model_service_validated ?? result.model_validated ?? result.ok));
    if (result.persisted) {
      setApiKey("");
      writeStoredAnalysisMode(modeToSave);
      await setup.refetch();
    }
    setBusy(null);
  };

  const onRepair = async () => {
    if (busy) return;
    setBusy("repair");
    setUserMessage("");
    const result = await repairRecommendedQwenSetup({
      cloudBodyConsent: cloudBodyConsent || null,
      qc,
    });
    setUserMessage(stripRawErrorCodes(result.user_message));
    setTestErrorCode(result.error_code || null);
    await setup.refetch();
    setBusy(null);
  };

  const disconnect = async () => {
    if (busy) return;
    setBusy("disconnect");
    try {
      await providersApi.action(DEFAULT_AI_SERVICE_ID, "disconnect");
      const latest = await providersApi.configuration(DEFAULT_AI_SERVICE_ID);
      qc.setQueryData(["provider-config", DEFAULT_AI_SERVICE_ID], latest);
      await setup.refetch();
      setUserMessage("已断开 AI 服务连接。");
      setTestErrorCode(null);
      setModelValidated(false);
    } catch (error: any) {
      setUserMessage(error?.message || "断开失败");
    } finally {
      setBusy(null);
    }
  };

  if (providers.isLoading || configuration.isLoading || setup.isLoading || cloud.isLoading) {
    return (
      <article className="settings-panel">
        <Loading />
      </article>
    );
  }

  // Backend SQLite is the sole source for these flags — never invent false before hydrate.
  const apiKeyConfigured = Boolean(setup.data?.credential_configured ?? view.apiKeyConfigured);
  const providerEnabled = Boolean(setup.data?.provider_enabled ?? configuration.data?.enabled);
  const cloudEnabled = Boolean(setup.data?.cloud_enabled ?? cloud.data?.enabled);
  const profile = setup.data?.config_profile;
  const pricingOk = !(setup.data?.blockers || []).some((b) =>
    /pricing|BUDGET_NOT_AVAILABLE|MODEL_PRICING/i.test(b),
  );
  const budgetOk = !(setup.data?.blockers || []).some((b) =>
    /budget_unavailable|INSUFFICIENT_BUDGET/i.test(b),
  );
  const rateLimited =
    testErrorCode === "RATE_LIMITED" ||
    testErrorCode === "rate_limited" ||
    /rate_limited|429/i.test(userMessage);

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-ai-service">
      <header className="settings-panel-header">
        <h2>AI 服务</h2>
        <p>连接所选模型服务完成章节分析。Endpoint 与模型 ID 将随分析模式自动配置。</p>
      </header>

      {profile && (
        <div
          className="notice"
          data-testid="ai-config-environment-banner"
          data-runtime-mode={profile.runtime_mode}
        >
          <b>
            {profile.runtime_mode === "browser_dev"
              ? "当前为浏览器开发模式"
              : profile.runtime_mode === "desktop_dev"
                ? "当前为桌面开发模式"
                : "当前为正式安装版"}
          </b>
          <p>{profile.user_message}</p>
          <p className="hint">
            配置库：{profile.data_directory}
            {profile.isolates_sqlite_from_packaged && profile.packaged_data_directory_hint
              ? ` · 正式版目录：${profile.packaged_data_directory_hint}`
              : ""}
          </p>
          {!profile.credential_store.desktop_parity && (
            <p className="hint" data-testid="ai-credential-capability-note">
              当前凭据能力与桌面正式版不完全一致（store=
              {profile.credential_store.type}，available=
              {String(profile.credential_store.available)}）。界面不会返回完整 API Key。
            </p>
          )}
        </div>
      )}

      <div className="ai-status-card" data-testid="ai-service-status-card">
        <div className="ai-status-main">
          <div>
            <p className="eyebrow">分析就绪</p>
            <span
              className={`ai-status-badge ${eligible ? "ok" : "warn"}`}
              data-testid="ai-service-connection-status"
              style={{ whiteSpace: "pre-line" }}
            >
              {rateLimited
                ? "配置完整，但模型请求受到服务商限流"
                : readinessLabel}
            </span>
          </div>
        </div>
        <ul className="ai-status-facts settings-ai-facts" data-testid="ai-service-status-facts">
          <li>凭据状态：{apiKeyConfigured ? "已配置" : "未配置"}</li>
          <li>网络状态：请使用「传输诊断」（高级）单独检查</li>
          <li>
            模型验证：
            {rateLimited
              ? "配置可用；最近一次请求 rate_limited (HTTP 429)"
              : modelValidated || eligible
                ? "已通过或可分析"
                : "尚未验证"}
          </li>
          <li>计价状态：{pricingOk && apiKeyConfigured ? "可用" : "缺失或未就绪"}</li>
          <li>预算状态：{budgetOk && apiKeyConfigured ? "可用" : "不足或未就绪"}</li>
          <li>Provider：{providerEnabled ? "已启用" : "未启用"}</li>
          <li>云端分析：{cloudEnabled ? "已开启" : "未开启"}</li>
          <li>
            正文发送同意（已持久化）：
            {setup.data?.cloud_body_consent ? "是" : "否"}
          </li>
          <li>最终分析就绪：{eligible ? "是" : "否"}</li>
          <li data-testid="ai-service-default-provider-label">默认服务：阿里云百炼（推荐）</li>
          <li>分析模式：{setup.data?.analysis_mode || analysisMode}</li>
        </ul>
        {rateLimited && (
          <p className="hint" data-testid="ai-service-rate-limited-detail">
            AI 服务配置已完成；Provider {providerEnabled ? "已启用" : "未启用"}；模型请求受到服务商限流。
            HTTP status：429；error_category：rate_limited；retryable：true。
          </p>
        )}
        {!eligible && !rateLimited && primaryBlocker && (
          <p className="hint" data-testid="ai-service-readiness-detail">
            {formatSetupErrorBlock(primaryBlocker, { model: view.modelDisplayName })}
          </p>
        )}
        {apiKeyConfigured && (!cloudEnabled || !providerEnabled) && profile?.isolates_sqlite_from_packaged && (
          <p className="hint" data-testid="ai-service-env-mismatch-hint">
            本机凭据库显示已配置，但当前开发配置库中云端/Provider 开关未开启。
            这通常是因为开发版与正式版使用不同的 SQLite，并不代表正式版配置被重置。
            请在本环境勾选正文发送说明后点击「验证并保存」，或使用「修复配置」。
          </p>
        )}
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
            placeholder={apiKeyConfigured ? "已配置；留空表示不修改" : "粘贴你的 API Key"}
            onChange={(e) => setApiKey(e.target.value)}
          />
        </label>
        <p className="hint" data-testid="ai-service-api-key-state">
          凭据状态：{apiKeyConfigured ? "已配置" : "未配置"}（界面不会显示完整 Key）
        </p>

        <label className="consent">
          <input
            type="checkbox"
            checked={cloudBodyConsent}
            data-testid="cloud-body-consent"
            onChange={(e) => setCloudBodyConsent(e.target.checked)}
          />
          为完成分析，StoryLens 将应用大模型能力对所选章节正文进行分析，所选正文会发送至当前模型服务商。正文不会进入
          StoryLens 匿名使用统计。费用由我的模型服务账户承担。
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
          disabled={Boolean(busy) || (!apiKeyConfigured && !apiKey)}
          onClick={() => void onVerify()}
        >
          {busy === "verify" ? "验证中…" : "验证模型服务"}
        </button>
        <button
          type="button"
          className="primary"
          data-testid="ai-service-save"
          disabled={Boolean(busy) || (!apiKey && !apiKeyConfigured)}
          onClick={() => void onSave()}
        >
          {busy === "save" ? "保存中…" : "验证并保存"}
        </button>
        {setup.data?.needs_cloud_consent && (
          <button
            type="button"
            data-testid="ai-service-repair"
            disabled={Boolean(busy)}
            onClick={() => void onRepair()}
          >
            修复配置
          </button>
        )}
        {showAdvanced && (
          <button
            type="button"
            data-testid="ai-service-disconnect"
            disabled={Boolean(busy) || !apiKeyConfigured}
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
          {JSON.stringify(
            {
              setup: setup.data,
              viewDiagnostics: view.diagnostics,
              error_code: testErrorCode,
            },
            null,
            2,
          )}
        </pre>
      )}

      <p className="hint" data-testid="ai-service-usage-quota-link">
        需要调整本地每日请求 / Token / 费用上限？请打开{" "}
        <Link to="/settings?tab=cost">使用额度</Link>。
      </p>

      {(developerMode || showAdvanced) && (
        <p className="hint">
          需要自定义 Endpoint 或 Model ID？请打开 <Link to="/settings?tab=advanced">高级设置</Link>
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
