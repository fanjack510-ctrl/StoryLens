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

type UiState =
  | "NOT_CONFIGURED"
  | "CONFIGURED_NOT_VERIFIED"
  | "VERIFYING"
  | "VERIFIED"
  | "CONFIG_CHANGED"
  | "VERIFICATION_FAILED"
  | "CONSENT_REQUIRED"
  | "READY";

function primaryLabelFor(state: UiState): string {
  switch (state) {
    case "NOT_CONFIGURED":
      return "保存并验证";
    case "CONSENT_REQUIRED":
      return "保存同意";
    case "CONFIGURED_NOT_VERIFIED":
      return "验证连接";
    case "VERIFYING":
      return "正在验证…";
    default:
      return "重新验证";
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
  const [consentHydrated, setConsentHydrated] = useState(false);
  const [busy, setBusy] = useState<"verify" | "save" | "repair" | "disconnect" | null>(null);
  const [userMessage, setUserMessage] = useState("");
  const [showConnectionDetails, setShowConnectionDetails] = useState(false);
  const [showEnvDetails, setShowEnvDetails] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [testErrorCode, setTestErrorCode] = useState<string | null>(null);

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

  useEffect(() => {
    if (!setup.data || consentHydrated) return;
    setCloudBodyConsent(Boolean(setup.data.cloud_body_consent));
    setConsentHydrated(true);
  }, [setup.data, consentHydrated]);

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
    setUserMessage(stripRawErrorCodes(result.user_message || "模型服务验证成功。"));
    setTestErrorCode(result.error_code || null);
    await setup.refetch();
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
    if (result.persisted) {
      setApiKey("");
      writeStoredAnalysisMode(modeToSave);
    }
    await setup.refetch();
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

  const serverState = (setup.data?.connection_ui_state || "") as UiState | "";
  const uiState: UiState =
    busy === "verify" || busy === "save"
      ? "VERIFYING"
      : serverState === "NOT_CONFIGURED" ||
          serverState === "CONFIGURED_NOT_VERIFIED" ||
          serverState === "VERIFIED" ||
          serverState === "CONFIG_CHANGED" ||
          serverState === "VERIFICATION_FAILED" ||
          serverState === "CONSENT_REQUIRED" ||
          serverState === "READY"
        ? serverState
        : !apiKeyConfigured
          ? "NOT_CONFIGURED"
          : "CONFIGURED_NOT_VERIFIED";

  const statusLabel =
    uiState === "VERIFYING"
      ? "正在验证"
      : setup.data?.connection_ui_label ||
        (uiState === "READY"
          ? "可以开始分析"
          : uiState === "VERIFIED"
            ? "验证成功"
            : uiState === "CONSENT_REQUIRED"
              ? "连接已验证，分析前需确认正文发送"
              : uiState === "CONFIG_CHANGED"
                ? "配置已更改，需要重新验证"
                : uiState === "VERIFICATION_FAILED"
                  ? "验证失败"
                  : uiState === "NOT_CONFIGURED"
                    ? "尚未配置"
                    : "已配置，尚未验证");

  const statusReason =
    uiState === "VERIFYING"
      ? "正在连接模型服务并保存验证结果…"
      : setup.data?.connection_ui_reason ||
        (uiState === "NOT_CONFIGURED"
          ? "请完成模型服务配置。"
          : "请验证模型服务后再开始分析。");

  const validatedAtDisplay =
    setup.data?.validated_at_display ||
    (setup.data?.validation_snapshot as { validated_at_display?: string } | null | undefined)
      ?.validated_at_display ||
    null;
  const validatedModel =
    setup.data?.validated_model || view.modelDisplayName || configuration.data?.plus_model || "—";

  const primaryLabel = primaryLabelFor(uiState);
  const runPrimary = () => {
    if (uiState === "NOT_CONFIGURED" || uiState === "CONSENT_REQUIRED" || apiKey) {
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

      <section
        className="settings-hero-card"
        data-testid="ai-service-status-card"
        data-connection-ui-state={uiState}
      >
        <header className="settings-panel-header">
          <h2>AI模型服务</h2>
        </header>
        <p
          className={`settings-status-line settings-status-${uiState.toLowerCase()}`}
          data-testid="ai-service-connection-status"
        >
          {statusLabel}
        </p>
        <p className="settings-status-reason" data-testid="ai-service-status-reason">
          {statusReason}
        </p>
        <dl className="settings-status-meta" data-testid="ai-service-status-meta">
          <div>
            <dt>当前服务</dt>
            <dd data-testid="ai-service-current-provider">阿里云百炼</dd>
          </div>
          <div>
            <dt>当前模型</dt>
            <dd data-testid="ai-service-current-model">{validatedModel}</dd>
          </div>
          {validatedAtDisplay ? (
            <div>
              <dt>最近验证</dt>
              <dd data-testid="ai-service-validated-at">{validatedAtDisplay}</dd>
            </div>
          ) : null}
        </dl>
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
        {!eligible && !rateLimited && primaryBlocker && uiState !== "READY" && (
          <p className="hint" data-testid="ai-service-readiness-detail">
            {formatSetupErrorBlock(primaryBlocker, { model: view.modelDisplayName })}
          </p>
        )}
        <ul className="ai-status-facts settings-ai-facts visually-hidden" data-testid="ai-service-status-facts">
          <li>凭据状态：{apiKeyConfigured ? "已配置" : "未配置"}</li>
          <li>Provider：{providerEnabled ? "已启用" : "未启用"}</li>
          <li>云端分析：{cloudEnabled ? "已开启" : "未开启"}</li>
          <li>最终分析就绪：{uiState === "READY" ? "是" : "否"}</li>
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
            disabled={
              Boolean(busy) ||
              (!apiKey && !apiKeyConfigured) ||
              (uiState === "CONSENT_REQUIRED" && !cloudBodyConsent)
            }
            onClick={() => runPrimary()}
          >
            {busy === "save" || busy === "verify" ? "正在验证…" : primaryLabel}
          </button>
          {/* Hidden alias keeps older test hooks calling verify-without-save */}
          <button
            type="button"
            className="visually-hidden"
            tabIndex={-1}
            data-testid="ai-service-test"
            disabled={Boolean(busy) || (!apiKeyConfigured && !apiKey)}
            onClick={() => void onVerify()}
            aria-hidden
          >
            验证模型服务
          </button>
          {setup.data?.needs_cloud_consent && uiState !== "CONSENT_REQUIRED" && (
            <button
              type="button"
              data-testid="ai-service-repair"
              disabled={Boolean(busy)}
              onClick={() => void onRepair()}
            >
              修复配置
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
            <li>配置状态：{apiKeyConfigured ? "已配置" : "未配置"}</li>
            <li>验证状态：{setup.data?.connection_ui_state || uiState}</li>
            <li>服务状态：{providerEnabled ? "已启用" : "未启用"}</li>
            <li>云端开关：{cloudEnabled ? "已开启" : "未开启"}</li>
            <li>模型：{validatedModel}</li>
            <li>Endpoint Host：{(setup.data?.validation_snapshot as { endpoint_host?: string } | null)?.endpoint_host || "—"}</li>
            <li>最近验证：{validatedAtDisplay || "—"}</li>
            <li>正文发送同意：{setup.data?.cloud_body_consent ? "是" : "否"}</li>
            {testErrorCode ? <li>最近错误：{mapSetupError(testErrorCode, { model: validatedModel }).title}</li> : null}
          </ul>
          <button
            type="button"
            data-testid="ai-service-disconnect"
            disabled={Boolean(busy) || !apiKeyConfigured}
            onClick={() => void disconnect()}
          >
            断开模型服务
          </button>
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
