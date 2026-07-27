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
import { stripRawErrorCodes } from "../../services/setupErrorCopy";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { Button } from "../ui/Button";

type Step = 1 | 2;

const MODE_HINT: Record<"FAST" | "BALANCED" | "QUALITY", string> = {
  FAST: "速度优先，适合初步拆解",
  BALANCED: "推荐，兼顾成本和质量",
  QUALITY: "适合关键章节和最终分析",
};

export function FirstLaunchWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const complete = useOnboardingStore((s) => s.complete);
  const setupStatus = useQuery({
    queryKey: ["recommended-qwen-setup"],
    queryFn: fetchRecommendedQwenStatus,
  });
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(DEFAULT_ANALYSIS_MODE);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  const hasExistingCredential = Boolean(setupStatus.data?.credential_configured);

  const enterLibrary = () => {
    complete();
    navigate("/library");
  };

  const mode = (analysisMode === "CUSTOM" ? DEFAULT_ANALYSIS_MODE : analysisMode) as
    | "FAST"
    | "BALANCED"
    | "QUALITY";

  const primaryLabel = useMemo(() => {
    if (busy) return "正在验证…";
    if (failed) return "重新验证";
    if (hasExistingCredential && !apiKey.trim()) return "验证并进入书库";
    return "保存并验证";
  }, [busy, failed, hasExistingCredential, apiKey]);

  const onVerify = async () => {
    if (!consent) {
      setMessage("请先勾选正文发送同意。");
      setFailed(true);
      return;
    }
    if (!apiKey.trim() && !hasExistingCredential) {
      setMessage("请填写 API Key 后再试。");
      setFailed(true);
      return;
    }
    setBusy(true);
    setMessage("");
    setFailed(false);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: mode,
      cloudBodyConsent: consent,
      persist: true,
      qc,
    });
    const ready = Boolean(
      result.analysis_ready ?? (result.ok && result.persisted && result.provider_eligible),
    );
    setBusy(false);
    if (result.persisted) {
      setApiKey("");
    }
    if (result.ok && ready && result.persisted) {
      enterLibrary();
      return;
    }
    setFailed(true);
    setMessage(stripRawErrorCodes(result.user_message) || "验证失败，请检查 API Key 后重试。");
  };

  return (
    <div className="onboarding-overlay" data-testid="first-launch-wizard" role="dialog" aria-modal="true">
      <div className="onboarding-card onboarding-card--wizard onboarding-card--compact">
        {step === 1 && (
          <div data-testid="onboarding-step-welcome" className="onboarding-welcome onboarding-welcome--v2">
            <h2 className="onboarding-welcome-title">欢迎使用 StoryLens</h2>
            <p className="onboarding-welcome-lead">拆解场景、追踪钩子，理解整本故事。</p>
            <p className="muted onboarding-welcome-privacy">书籍与分析结果默认保存在本机。</p>
            <div className="onboarding-welcome-actions">
              <Button
                variant="primary"
                data-testid="onboarding-start-setup"
                onClick={() => setStep(2)}
              >
                开始设置
              </Button>
              <button
                type="button"
                className="linkish"
                data-testid="onboarding-enter-library"
                onClick={enterLibrary}
              >
                先进入书库
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div data-testid="onboarding-step-ai" className="onboarding-ai onboarding-ai--v2">
            <header className="onboarding-ai-header">
              <h2 className="onboarding-step-title">连接 AI 模型</h2>
            </header>

            <div className="onboarding-field-row" data-testid="onboarding-current-service">
              <span className="onboarding-field-label">当前服务</span>
              <strong>阿里云百炼</strong>
            </div>

            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                autoComplete="new-password"
                value={apiKey}
                data-testid="onboarding-api-key"
                placeholder={
                  hasExistingCredential ? "已配置，留空表示不修改" : "粘贴你的 API Key"
                }
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setFailed(false);
                  setMessage("");
                }}
              />
              <small className="field-hint">Key仅保存在本机。</small>
            </label>

            <label className="settings-field">
              <span>分析模式</span>
              <select
                value={analysisMode}
                aria-label="分析模式"
                data-testid="onboarding-analysis-mode"
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
                consent ? "onboarding-consent-box--checked" : "onboarding-consent-box--unchecked"
              }`}
              data-testid="onboarding-consent-box"
              data-consent={consent ? "checked" : "unchecked"}
            >
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              <span>
                分析时，允许将所选正文发送给当前模型服务商
                <em>StoryLens不会将正文上传到自己的服务器。</em>
              </span>
            </label>

            {message ? (
              <p
                className={`onboarding-inline-message ${failed ? "is-error" : ""}`}
                data-testid="onboarding-ai-message"
                role="status"
              >
                {message}
              </p>
            ) : null}

            <div className="onboarding-ai-actions">
              <Button
                variant="primary"
                className="onboarding-btn-fixed"
                disabled={busy || (!apiKey.trim() && !hasExistingCredential) || !consent}
                onClick={() => void onVerify()}
                data-testid="onboarding-test"
              >
                {primaryLabel}
              </Button>
              <div className="onboarding-ai-secondary">
                <Link
                  to="/settings?tab=advanced"
                  className="linkish"
                  data-testid="onboarding-other-ai"
                  onClick={() => complete()}
                >
                  使用其他AI服务
                </Link>
                <button
                  type="button"
                  className="linkish"
                  data-testid="onboarding-skip-config"
                  onClick={enterLibrary}
                >
                  稍后配置
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
