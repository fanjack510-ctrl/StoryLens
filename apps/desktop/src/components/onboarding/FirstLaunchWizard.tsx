import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import { fetchAiConnection } from "../../services/aiConnection";
import { providersApi } from "../../services/providersApi";
import { settingsApi } from "../../services/settingsApi";
import { writeStoredAnalysisMode } from "../../services/analysisModePresets";
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
  // 这一步以前写死「阿里云百炼」，走的是只为通义千问准备的一键配置。新用户因此只有一条路，
  // 而设置页里明明能选 DeepSeek。现在向导和设置页读同一份状态、走同一套保存与验证。
  const setupStatus = useQuery({
    queryKey: ["ai-connection"],
    queryFn: fetchAiConnection,
  });
  const active = useQuery({
    queryKey: ["active-cloud-provider"],
    queryFn: settingsApi.activeCloudProvider,
  });
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(DEFAULT_ANALYSIS_MODE);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  const hasExistingCredential = Boolean(setupStatus.data?.credential_configured);
  const options = active.data?.options ?? [];
  const [providerId, setProviderId] = useState("");
  const selectedId = providerId || active.data?.provider_name || options[0]?.name || "";

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
    try {
      const current = await providersApi.configuration(selectedId);
      await providersApi.save(selectedId, {
        display_name: current.display_name,
        region: current.region || "",
        workspace_id: current.workspace_id || "",
        base_url: current.base_url || null,
        plus_model: current.plus_model,
        max_model: current.max_model || current.plus_model,
        flash_model: current.flash_model || current.plus_model,
        timeout_seconds: current.timeout_seconds ?? 300,
        max_retries: current.max_retries ?? 3,
        enabled: true,
        disconnected: false,
        allow_auto_route: Boolean(current.allow_auto_route),
        raw_logging_enabled: Boolean(current.raw_logging_enabled),
        api_key: apiKey || null,
      });
      await settingsApi.setActiveCloudProvider(selectedId);
      await settingsApi.setCloud(true);
      await settingsApi.setCloudBodyConsent(consent);
      writeStoredAnalysisMode(mode);
      // 传输诊断证明管子通，真实调用才写下分析预检要读的那份验证快照。少了后者，
      // 24 小时后「分析本章」会永久变灰，而向导里看起来一切正常。
      await providersApi.transportDiagnostic(selectedId);
      await providersApi.testConnection(selectedId, 32);
      setApiKey("");
      await qc.invalidateQueries({ queryKey: ["ai-connection"] });
      enterLibrary();
    } catch (error: unknown) {
      setFailed(true);
      const code = String((error as { code?: string })?.code || "");
      setMessage(
        code === "PROVIDER_AUTHENTICATION_FAILED" || code.includes("401")
          ? "API Key 无效，请检查后重试。"
          : code === "PROVIDER_INSUFFICIENT_BALANCE" || code.includes("402")
            ? "服务商账户余额不足。"
            : error instanceof Error
              ? error.message
              : "验证失败，请检查 API Key 后重试。",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="onboarding-overlay" data-testid="first-launch-wizard" role="dialog" aria-modal="true">
      <div className="onboarding-card onboarding-card--wizard onboarding-card--compact">
        {step === 1 && (
          <div data-testid="onboarding-step-welcome" className="onboarding-welcome onboarding-welcome--v2">
            <h2 className="onboarding-welcome-title">欢迎使用 StoryLens</h2>
            {/* 原来这里写的是「拆解场景、追踪钩子，理解整本故事」——三个内部词，
                新用户读不出这是三件事还是一件事，更读不出自己能拿它做什么。
                这是全产品的第一屏，也是唯一一次能一句话说清「这是什么」的机会，
                而它被用来做了一句口号。换成三种读法各一行：说的是**你能拿它做什么**，
                而且和后面真正要选的那三个选项用的是同一套词。 */}
            <p className="onboarding-welcome-lead">导入一本书，选一种读法。</p>
            <ul className="onboarding-welcome-readings">
              <li>
                <b>评测</b>看自己的书：该改哪里、为什么
              </li>
              <li>
                <b>拆文</b>看别人的书：起承转合、钩子怎么下
              </li>
              <li>
                <b>读懂</b>看不是小说的书：专著、教材、工具书
              </li>
            </ul>
            <p className="muted onboarding-welcome-privacy">
              书籍与分析结果默认保存在本机。装好之后顶栏的「能做什么」里有完整清单。
            </p>
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

            <label className="settings-field" data-testid="onboarding-current-service">
              <span>AI 服务商</span>
              <select
                value={selectedId}
                aria-label="AI 服务商"
                data-testid="onboarding-provider-select"
                onChange={(e) => setProviderId(e.target.value)}
              >
                {options.map((o) => (
                  <option key={o.name} value={o.name}>
                    {o.display_name || o.name}
                  </option>
                ))}
              </select>
            </label>

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
