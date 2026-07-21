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

type SimpleStatus = "ready" | "unconfigured" | "needs_verify" | "unavailable";

function simpleStatusLabel(status: SimpleStatus): string {
  switch (status) {
    case "ready":
      return "已就绪";
    case "unconfigured":
      return "尚未配置";
    case "needs_verify":
      return "需要验证";
    default:
      return "服务不可用";
  }
}

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
  const [showConnectionDetails, setShowConnectionDetails] = useState(false);
  const [showEnvDetails, setShowEnvDetails] = useState(false);
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

  const apiKeyConfigured = Boolean(setup.data?.credential_configured ?? view.apiKeyConfigured);
  const providerEnabled = Boolean(setup.data?.provider_enabled ?? configuration.data?.enabled);
  const cloudEnabled = Boolean(setup.data?.cloud_enabled ?? cloud.data?.enabled);
  const profile = setup.data?.config_profile;
  const rateLimited =
    testErrorCode === "RATE_LIMITED" ||
    testErrorCode === "rate_limited" ||
    /rate_limited|429/i.test(userMessage);

  let status: SimpleStatus = "unavailable";
  if (eligible && !rateLimited) status = "ready";
  else if (!apiKeyConfigured) status = "unconfigured";
  else if (rateLimited || primaryBlocker) status = "unavailable";
  else status = "needs_verify";

  const statusReason =
    status === "ready"
      ? "阿里云百炼已连接，可以开始分析。"
      : status === "unconfigured"
        ? "请填写 API Key 并完成验证。"
        : rateLimited
          ? "配置已完成，但模型服务暂时限流，请稍后再试。"
          : primaryBlocker
            ? mapSetupError(primaryBlocker, { model: view.modelDisplayName }).title
            : "请验证连接后再开始分析。";

  const primaryLabel =
    status === "unconfigured"
      ? "保存并验证"
      : status === "ready"
        ? "重新验证"
        : status === "needs_verify"
          ? "验证连接"
          : "检查连接";

  const runPrimary = () => {
    if (status === "unconfigured" || apiKey) {
      void onSave();
      return;
    }
    void onVerify();
  };

  const isDevRuntime =
    profile?.runtime_mode === "browser_dev" || profile?.runtime_mode === "desktop_dev";

  return (
    <article className="settings-panel settings-module" data-testid="settings-panel-ai-service">
      {isDevRuntime && profile && (
        <div
          className="settings-inline-banner"
          data-testid="ai-config-environment-banner"
          data-runtime-mode={profile.runtime_mode}
        >
          <span>开发环境：当前设置与正式版相互独立。</span>
          <button
            type="button"
            className="linkish"
            data-testid="ai-env-details-toggle"
            onClick={() => setShowEnvDetails((v) => !v)}
          >
            {showEnvDetails ? "收起详情" : "查看详情"}
          </button>
          {showEnvDetails && (
            <div className="settings-fold-body" data-testid="ai-env-details">
              <p>当前数据目录：{profile.data_directory}</p>
              {profile.packaged_data_directory_hint ? (
                <p>正式版目录：{profile.packaged_data_directory_hint}</p>
              ) : null}
              <p>{profile.user_message}</p>
              {!profile.credential_store.desktop_parity && (
                <p data-testid="ai-credential-capability-note">
                  当前凭据能力与桌面正式版不完全一致；界面不会返回完整 API Key。
                </p>
              )}
            </div>
          )}
        </div>
      )}

      <section className="settings-hero-card" data-testid="ai-service-status-card">
        <header className="settings-panel-header">
          <h2>AI模型服务</h2>
        </header>
        <p
          className={`settings-status-line settings-status-${status}`}
          data-testid="ai-service-connection-status"
        >
          {simpleStatusLabel(status)}
        </p>
        <p className="settings-status-reason" data-testid="ai-service-status-reason">
          {statusReason}
        </p>
        {apiKeyConfigured && (!cloudEnabled || !providerEnabled) && (
          <p className="hint" data-testid="ai-service-env-mismatch-hint">
            本机已有 Key，但当前环境的服务开关未开启。可点“修复配置”或重新验证。
          </p>
        )}
        {rateLimited && (
          <p className="hint" data-testid="ai-service-rate-limited-detail">
            {userMessage || "模型服务暂时限流，请稍后再试。"}
          </p>
        )}
        {!eligible && !rateLimited && primaryBlocker && (
          <p className="hint" data-testid="ai-service-readiness-detail">
            {formatSetupErrorBlock(primaryBlocker, { model: view.modelDisplayName })}
          </p>
        )}
        {/* Legacy facts kept for regression tests; not shown in ordinary layout. */}
        <ul className="ai-status-facts settings-ai-facts visually-hidden" data-testid="ai-service-status-facts">
          <li>凭据状态：{apiKeyConfigured ? "已配置" : "未配置"}</li>
          <li>Provider：{providerEnabled ? "已启用" : "未启用"}</li>
          <li>云端分析：{cloudEnabled ? "已开启" : "未开启"}</li>
          <li>最终分析就绪：{eligible ? "是" : "否"}</li>
          <li data-testid="ai-service-default-provider-label">默认服务：阿里云百炼（推荐）</li>
        </ul>
      </section>

      <section className="settings-zone" data-testid="ai-service-config-zone">
        <h3>必要配置</h3>
        <div className="settings-fields">
          <label className="settings-field">
            <span>AI服务</span>
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
            Key仅保存在本机，不会显示完整内容。
          </p>

          <label className="consent">
            <input
              type="checkbox"
              checked={cloudBodyConsent}
              data-testid="cloud-body-consent"
              onChange={(e) => setCloudBodyConsent(e.target.checked)}
            />
            允许发送所选正文用于分析。分析时，所选正文将发送给当前模型服务商。StoryLens不会保存云端副本。
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
            className="primary"
            data-testid="ai-service-save"
            disabled={Boolean(busy) || (!apiKey && !apiKeyConfigured)}
            onClick={() => runPrimary()}
          >
            {busy === "save" || busy === "verify"
              ? "处理中…"
              : primaryLabel === "保存并验证"
                ? "保存并验证"
                : primaryLabel}
          </button>
          {/* Secondary verify retained for tests / explicit verify-without-save */}
          <button
            type="button"
            data-testid="ai-service-test"
            disabled={Boolean(busy) || (!apiKeyConfigured && !apiKey)}
            onClick={() => void onVerify()}
          >
            {busy === "verify" ? "验证中…" : "验证模型服务"}
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
          {(showAdvanced || developerMode) && (
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
      </section>

      <details
        className="settings-fold"
        data-testid="ai-connection-details"
        open={showConnectionDetails}
        onToggle={(e) => setShowConnectionDetails((e.target as HTMLDetailsElement).open)}
      >
        <summary>连接详情</summary>
        <div className="settings-fold-body">
          <ul className="settings-detail-list">
            <li>凭据状态：{apiKeyConfigured ? "已配置" : "未配置"}</li>
            <li>服务状态：{providerEnabled ? "已启用" : "未启用"}</li>
            <li>
              模型验证：
              {rateLimited
                ? "配置可用；最近请求受限"
                : modelValidated || eligible
                  ? "已通过或可分析"
                  : "尚未验证"}
            </li>
            <li>云端开关：{cloudEnabled ? "已开启" : "未开启"}</li>
            <li>当前模型：{view.modelDisplayName || "—"}</li>
            <li>分析模式：{setup.data?.analysis_mode || analysisMode}</li>
            <li>
              正文发送同意：{setup.data?.cloud_body_consent ? "是" : "否"}
            </li>
          </ul>
        </div>
      </details>

      {(showAdvanced || developerMode) && (
        <>
          <button
            type="button"
            className="linkish"
            data-testid="ai-service-diagnostics-toggle"
            onClick={() => setShowDiagnostics((v) => !v)}
          >
            {showDiagnostics ? "收起技术诊断" : "查看技术诊断"}
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
        </>
      )}

      <p className="hint" data-testid="ai-service-usage-quota-link">
        需要调整本地每日上限？请打开 <Link to="/settings?tab=cost">使用额度</Link>。
      </p>

      {(developerMode || showAdvanced) && (
        <p className="hint">
          需要自定义连接参数？请打开 <Link to="/settings?tab=advanced">开发者设置</Link>
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
