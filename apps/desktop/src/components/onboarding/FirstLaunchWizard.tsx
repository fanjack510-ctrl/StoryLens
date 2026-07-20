import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import { DEFAULT_AI_SERVICE_ID } from "../../services/aiServiceViewModel";
import { saveAiServiceConfiguration, testAiServiceConnection } from "../../services/aiServiceConfig";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useTelemetryStore } from "../../stores/telemetry";

type Step = 1 | 2 | 3;

export function FirstLaunchWizard() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const complete = useOnboardingStore((s) => s.complete);
  const skip = useOnboardingStore((s) => s.skip);
  const setTelemetryEnabled = useTelemetryStore((s) => s.setAnonymousTelemetryEnabled);
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(DEFAULT_ANALYSIS_MODE);
  const [consent, setConsent] = useState(false);
  const [anonymousStats, setAnonymousStats] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

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

  const onTest = async () => {
    if (!consent) {
      setMessage("请先确认正文发送说明。");
      return;
    }
    setBusy(true);
    setMessage("");
    const saveResult = await saveAiServiceConfiguration({
      providerId: DEFAULT_AI_SERVICE_ID,
      apiKey,
      analysisMode,
      cloudBodyConsent: consent,
      qc,
    });
    if (!saveResult.ok && !apiKey) {
      const testResult = await testAiServiceConnection(DEFAULT_AI_SERVICE_ID, qc);
      setMessage(testResult.userMessage);
    } else {
      setMessage(saveResult.userMessage);
    }
    setBusy(false);
  };

  return (
    <div className="onboarding-overlay" data-testid="first-launch-wizard" role="dialog" aria-modal="true">
      <div className="onboarding-card">
        {step === 1 && (
          <div data-testid="onboarding-step-welcome">
            <h2>欢迎使用 StoryLens</h2>
            <p>
              StoryLens 是小说结构分析与深度阅读工具，帮助你理解章节节奏、场景与读者旅程——不是自动写小说工具。
            </p>
            <div className="settings-actions">
              <button type="button" className="linkish" onClick={onSkipAll}>
                跳过向导
              </button>
              <button type="button" className="primary" onClick={() => setStep(2)}>
                下一步
              </button>
            </div>
          </div>
        )}

        {step === 2 && (
          <div data-testid="onboarding-step-ai">
            <h2>连接 AI 服务</h2>
            <label className="settings-field">
              <span>AI 服务</span>
              <input readOnly value="阿里云百炼（推荐）" />
            </label>
            <label className="settings-field">
              <span>API Key</span>
              <input
                type="password"
                autoComplete="new-password"
                value={apiKey}
                data-testid="onboarding-api-key"
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
            <label className="settings-field">
              <span>分析模式</span>
              <select
                value={analysisMode}
                aria-label="分析模式"
                onChange={(e) => setAnalysisMode(e.target.value as AnalysisModePresetId)}
              >
                {ordinaryModeOptions().map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="consent">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              我确认分析时可发送章节正文至阿里云百炼。
            </label>
            {message && <p role="status">{message}</p>}
            <div className="settings-actions">
              <Link to="/settings?tab=advanced" className="linkish" onClick={() => skip()}>
                其他 AI 服务 / 本地模型
              </Link>
              <button type="button" className="linkish" onClick={() => setStep(3)}>
                稍后配置
              </button>
              <button type="button" disabled={busy} onClick={() => void onTest()}>
                {busy ? "测试中…" : "测试连接"}
              </button>
              <button type="button" className="primary" onClick={() => setStep(3)}>
                下一步
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div data-testid="onboarding-step-start">
            <h2>开始使用</h2>
            <p>导入第一本小说，或先浏览空书库；随时可在设置中修改 AI 配置。</p>
            <label className="consent" data-testid="onboarding-telemetry-opt-in">
              <input
                type="checkbox"
                checked={anonymousStats}
                onChange={(e) => setAnonymousStats(e.target.checked)}
              />
              允许发送匿名使用统计，帮助改进 StoryLens
            </label>
            <p className="muted">不包含小说正文、书名、文件路径或 API Key</p>
            <div className="settings-actions">
              <button type="button" className="primary" onClick={() => finish("import")}>
                导入第一本小说
              </button>
              <button type="button" onClick={() => finish("library")}>
                进入空书库
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
