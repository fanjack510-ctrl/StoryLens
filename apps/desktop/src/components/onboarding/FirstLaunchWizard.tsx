import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import {
  configureRecommendedQwenService,
  fetchRecommendedQwenStatus,
} from "../../services/aiServiceConfig";
import { nextBlockedReason, stripRawErrorCodes } from "../../services/setupErrorCopy";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useTelemetryStore } from "../../stores/telemetry";
import { Button } from "../ui/Button";

type Step = 1 | 2 | 3;
type BusyIntent = "verify_save" | null;

const MODE_HINT: Record<"FAST" | "BALANCED" | "QUALITY", string> = {
  FAST: "速度优先，适合初步拆解",
  BALANCED: "推荐，兼顾成本和质量",
  QUALITY: "适合关键章节和最终分析",
};

const STEP_META: Record<Step, { index: string; title: string }> = {
  1: { index: "步骤 1 / 3", title: "欢迎使用 StoryLens" },
  2: { index: "步骤 2 / 3", title: "连接 AI 服务" },
  3: { index: "步骤 3 / 3", title: "完成" },
};

export function FirstLaunchWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const complete = useOnboardingStore((s) => s.complete);
  const skip = useOnboardingStore((s) => s.skip);
  const setTelemetryEnabled = useTelemetryStore((s) => s.setAnonymousTelemetryEnabled);
  const setupStatus = useQuery({
    queryKey: ["recommended-qwen-setup"],
    queryFn: fetchRecommendedQwenStatus,
  });
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(DEFAULT_ANALYSIS_MODE);
  const [consent, setConsent] = useState(false);
  const [anonymousStats, setAnonymousStats] = useState(false);
  const [busyIntent, setBusyIntent] = useState<BusyIntent>(null);
  const [message, setMessage] = useState("");
  const [lastOk, setLastOk] = useState<boolean | null>(null);
  const [setupSaved, setSetupSaved] = useState(false);
  const [modelValidated, setModelValidated] = useState(false);
  const [analysisReady, setAnalysisReady] = useState(false);
  const [blockers, setBlockers] = useState<string[]>([]);
  const [readinessReasons, setReadinessReasons] = useState<string[]>([]);
  const [showTechDetails, setShowTechDetails] = useState(false);
  const [lastErrorCode, setLastErrorCode] = useState<string | null>(null);

  const busy = busyIntent !== null;
  const meta = STEP_META[step];
  const hasExistingCredential = Boolean(setupStatus.data?.credential_configured);

  const finish = (target: "library" | "import") => {
    setTelemetryEnabled(anonymousStats);
    complete();
    if (target === "import") {
      navigate("/library?import=1");
    } else {
      navigate("/library");
    }
  };

  const onSkipAll = () => {
    skip();
    navigate("/library");
  };

  const mode = (analysisMode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : analysisMode) as
    | "FAST"
    | "BALANCED"
    | "QUALITY";

  const canProceed = analysisReady && setupSaved && consent;
  const nextReason = useMemo(
    () =>
      nextBlockedReason({
        hasApiKeyInput: Boolean(apiKey.trim()),
        credentialConfigured: hasExistingCredential || setupSaved,
        modelValidated,
        persisted: setupSaved,
        analysisReady,
        cloudEnabled: Boolean(setupStatus.data?.cloud_enabled) || setupSaved,
        blockers,
      }),
    [
      apiKey,
      hasExistingCredential,
      setupSaved,
      modelValidated,
      analysisReady,
      setupStatus.data?.cloud_enabled,
      blockers,
    ],
  );

  const onVerifyAndSave = async () => {
    if (!consent) {
      setMessage("请先确认正文发送说明。");
      setLastOk(false);
      setLastErrorCode("CLOUD_CONSENT_REQUIRED");
      return;
    }
    if (!apiKey.trim() && !hasExistingCredential) {
      setMessage("请填写 API Key 后再试。");
      setLastOk(false);
      setLastErrorCode("CREDENTIAL_MISSING");
      return;
    }
    setBusyIntent("verify_save");
    setMessage("");
    setLastOk(null);
    setShowTechDetails(false);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: mode,
      cloudBodyConsent: consent,
      persist: true,
      qc,
    });
    const ready = Boolean(result.analysis_ready ?? (result.ok && result.persisted && result.provider_eligible));
    setMessage(stripRawErrorCodes(result.user_message));
    setLastOk(result.ok && ready);
    setModelValidated(Boolean(result.model_service_validated ?? result.model_validated ?? result.ok));
    setAnalysisReady(ready);
    setBlockers(result.blockers || []);
    setReadinessReasons(result.readiness_reasons || []);
    setLastErrorCode(result.error_code || null);
    setBusyIntent(null);
    if (result.persisted) {
      setSetupSaved(true);
      setApiKey("");
    } else {
      setSetupSaved(false);
    }
  };

  const onNext = () => {
    if (!canProceed) return;
    setStep(3);
  };

  const connectionStatus = (() => {
    if (busyIntent === "verify_save") {
      return {
        tone: "info" as const,
        title: "正在验证模型服务",
        detail: "正在检查 API Key、模型和接口响应。",
      };
    }
    if (analysisReady && setupSaved) {
      return {
        tone: "success" as const,
        title: "配置完成",
        detail: message || "模型服务、计价和预算检查均已通过，可以开始分析。",
      };
    }
    if (modelValidated && setupSaved && !analysisReady) {
      return {
        tone: "warning" as const,
        title: "模型服务验证成功",
        detail:
          message ||
          "API Key 和模型可以正常使用，但分析配置尚未完成。",
      };
    }
    if (lastOk === false) {
      return {
        tone: "danger" as const,
        title: "模型服务验证失败",
        detail: message || "API Key 无效或模型服务拒绝了请求。",
      };
    }
    if (!apiKey.trim() && !hasExistingCredential && lastOk === null) {
      return {
        tone: "neutral" as const,
        title: "尚未配置",
        detail: "填写 API Key 后验证模型服务。",
      };
    }
    return {
      tone: "neutral" as const,
      title: "尚未配置",
      detail: message || "填写 API Key 后验证模型服务。",
    };
  })();

  return (
    <div className="onboarding-overlay" data-testid="first-launch-wizard" role="dialog" aria-modal="true">
      <div className="onboarding-card onboarding-card--wizard">
        <header className="onboarding-card__header">
          <p className="onboarding-step-index">{meta.index}</p>
          <h2 className="onboarding-step-title">{meta.title}</h2>
        </header>

        <div className="onboarding-card__body">
          {step === 1 && (
            <div data-testid="onboarding-step-welcome" className="onboarding-welcome">
              <div className="onboarding-welcome-mark" aria-hidden="true">
                <span className="brand-mark">SL</span>
              </div>
              <h3>本地优先的小说拆解工具</h3>
              <p>
                StoryLens 是一款本地优先的小说结构分析与深度阅读工具。它可以帮助你整理章节、识别场景，并观察读者旅程。
              </p>
              <p className="muted">你的书籍默认保存在本机。</p>
            </div>
          )}

          {step === 2 && (
            <div data-testid="onboarding-step-ai" className="onboarding-ai">
              <section className="onboarding-service-card" aria-label="推荐服务">
                <div>
                  <strong>阿里云百炼</strong>
                  <p>当前模型服务 · 适合快速完成章节和全书分析</p>
                </div>
                <span className="onboarding-service-badge">推荐</span>
              </section>

              <label className="settings-field">
                <span>API Key</span>
                <input
                  type="password"
                  autoComplete="new-password"
                  value={apiKey}
                  data-testid="onboarding-api-key"
                  placeholder={
                    hasExistingCredential
                      ? "留空表示保持现有凭据"
                      : "粘贴你的 API Key"
                  }
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    setSetupSaved(false);
                    setAnalysisReady(false);
                    setModelValidated(false);
                    setLastOk(null);
                  }}
                />
                <small className="field-hint">
                  {hasExistingCredential
                    ? "API Key 仅保存在 Windows 凭据管理器中。留空表示保持现有凭据不变。"
                    : "API Key 仅保存在 Windows 凭据管理器中。"}
                </small>
              </label>

              <label className="settings-field">
                <span>分析偏好</span>
                <select
                  value={analysisMode}
                  aria-label="分析模式"
                  onChange={(e) => setAnalysisMode(e.target.value as AnalysisModePresetId)}
                >
                  {ordinaryModeOptions().map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.shortLabel}
                      {o.recommended ? "（推荐）" : ""}
                    </option>
                  ))}
                </select>
                <small className="field-hint">{MODE_HINT[mode]}</small>
              </label>

              <label
                className={`consent onboarding-consent-box ${
                  consent
                    ? "onboarding-consent-box--checked"
                    : "onboarding-consent-box--unchecked"
                }`}
                data-testid="onboarding-consent-box"
                data-consent={consent ? "checked" : "unchecked"}
              >
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>
                  为完成分析，StoryLens 需要调用所选模型服务，所选章节正文将发送至该模型服务商。
                  <em>正文不会进入 StoryLens 匿名使用统计。</em>
                </span>
              </label>

              <div
                className={`onboarding-status-card onboarding-status-card--${connectionStatus.tone}`}
                role="status"
                data-testid="onboarding-connection-status"
                data-tone={connectionStatus.tone}
              >
                <strong>{connectionStatus.title}</strong>
                <p data-testid="onboarding-ai-message">{connectionStatus.detail}</p>
                {modelValidated && setupSaved && !analysisReady && readinessReasons.length > 0 && (
                  <ul data-testid="onboarding-readiness-reasons">
                    {readinessReasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                )}
              </div>

              {lastErrorCode && (
                <details
                  className="onboarding-tech-details"
                  data-testid="onboarding-tech-details"
                  open={showTechDetails}
                  onToggle={(e) => setShowTechDetails((e.target as HTMLDetailsElement).open)}
                >
                  <summary>技术详情</summary>
                  <pre>{lastErrorCode}</pre>
                </details>
              )}

              {setupSaved && analysisReady && (
                <p data-testid="onboarding-ai-saved" className="hint">
                  配置已保存，可用于分析。
                </p>
              )}
            </div>
          )}

          {step === 3 && (
            <div data-testid="onboarding-step-start" className="onboarding-done">
              <h3>{setupSaved && analysisReady ? "配置完成" : "可以开始使用"}</h3>
              {setupSaved && analysisReady ? (
                <ul className="onboarding-done-checklist">
                  <li>✓ AI 服务已连接</li>
                  <li>✓ 分析模式已设置</li>
                  <li>✓ 数据默认保存在本机</li>
                </ul>
              ) : (
                <p>
                  可以先进入 StoryLens，但在完成 AI 服务配置前无法执行分析。导入第一本小说，或先浏览空书库；随时可在设置中修改
                  AI 配置。
                </p>
              )}
              <label className="consent" data-testid="onboarding-telemetry-opt-in">
                <input
                  type="checkbox"
                  checked={anonymousStats}
                  onChange={(e) => setAnonymousStats(e.target.checked)}
                />
                允许发送匿名使用统计，帮助改进 StoryLens
              </label>
              <p className="muted">不包含小说正文、书名、文件路径或 API Key</p>
            </div>
          )}
        </div>

        <footer className="onboarding-card__footer">
          {step === 1 && (
            <>
              <button type="button" className="linkish" onClick={onSkipAll}>
                跳过向导
              </button>
              <div className="onboarding-footer-right">
                <Button variant="primary" onClick={() => setStep(2)}>
                  下一步
                </Button>
              </div>
            </>
          )}
          {step === 2 && (
            <>
              <div className="onboarding-footer-left">
                <Link to="/settings?tab=advanced" className="linkish onboarding-alt-link" onClick={() => skip()}>
                  其他 AI 服务 / 本地模型
                </Link>
                <div className="onboarding-skip-block">
                  <Button variant="ghost" onClick={() => setStep(3)} data-testid="onboarding-skip-config">
                    稍后配置
                  </Button>
                  <p className="muted onboarding-skip-hint">
                    可以先进入 StoryLens，但在完成 AI 服务配置前无法执行分析。
                  </p>
                </div>
              </div>
              <div className="onboarding-footer-right">
                <Button
                  variant="secondary"
                  className="onboarding-btn-fixed"
                  disabled={busy || (!apiKey.trim() && !hasExistingCredential) || !consent}
                  onClick={() => void onVerifyAndSave()}
                  data-testid="onboarding-test"
                >
                  {busyIntent === "verify_save" ? "验证中…" : "验证并保存"}
                </Button>
                <div className="onboarding-next-wrap">
                  <Button
                    variant="primary"
                    className="onboarding-btn-fixed"
                    disabled={busy || !canProceed}
                    data-testid="onboarding-save-next"
                    onClick={onNext}
                  >
                    下一步
                  </Button>
                  {!canProceed && nextReason && (
                    <p className="muted onboarding-next-reason" data-testid="onboarding-next-reason">
                      {nextReason}
                    </p>
                  )}
                </div>
              </div>
            </>
          )}
          {step === 3 && (
            <div className="onboarding-footer-right onboarding-footer-right--alone">
              <Button variant="primary" onClick={() => finish("library")}>
                开始使用 StoryLens
              </Button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}
