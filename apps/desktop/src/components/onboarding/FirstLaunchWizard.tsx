import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  DEFAULT_ANALYSIS_MODE,
  ordinaryModeOptions,
  type AnalysisModePresetId,
} from "../../services/analysisModePresets";
import { configureRecommendedQwenService } from "../../services/aiServiceConfig";
import { useOnboardingStore } from "../../stores/onboardingStore";
import { useTelemetryStore } from "../../stores/telemetry";
import { Button } from "../ui/Button";

type Step = 1 | 2 | 3;
type BusyIntent = "test" | "save" | null;

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
  const [step, setStep] = useState<Step>(1);
  const [apiKey, setApiKey] = useState("");
  const [analysisMode, setAnalysisMode] = useState<AnalysisModePresetId>(DEFAULT_ANALYSIS_MODE);
  const [consent, setConsent] = useState(false);
  const [anonymousStats, setAnonymousStats] = useState(false);
  const [busyIntent, setBusyIntent] = useState<BusyIntent>(null);
  const [message, setMessage] = useState("");
  const [lastOk, setLastOk] = useState<boolean | null>(null);
  const [setupSaved, setSetupSaved] = useState(false);

  const busy = busyIntent !== null;
  const meta = STEP_META[step];

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

  const onTest = async () => {
    setBusyIntent("test");
    setMessage("");
    setLastOk(null);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: mode,
      cloudBodyConsent: consent,
      persist: false,
      qc,
    });
    setMessage(result.user_message);
    setLastOk(result.ok);
    setBusyIntent(null);
  };

  const onSaveAndNext = async () => {
    if (!consent) {
      setMessage("请先确认正文发送说明。");
      setLastOk(false);
      return;
    }
    setBusyIntent("save");
    setMessage("");
    setLastOk(null);
    const result = await configureRecommendedQwenService({
      apiKey,
      analysisMode: mode,
      cloudBodyConsent: consent,
      persist: true,
      qc,
    });
    setMessage(result.user_message);
    setLastOk(result.ok);
    setBusyIntent(null);
    if (result.ok && result.persisted && result.provider_eligible) {
      setSetupSaved(true);
      setStep(3);
      return;
    }
    setSetupSaved(false);
  };

  const connectionStatus = (() => {
    if (busyIntent === "test") {
      return { tone: "info" as const, title: "正在测试连接", detail: "请稍候…" };
    }
    if (busyIntent === "save") {
      return { tone: "info" as const, title: "正在保存配置", detail: "请稍候…" };
    }
    if (setupSaved) {
      return { tone: "success" as const, title: "配置已保存", detail: message || "可用于分析。" };
    }
    if (!message && lastOk === null) {
      return { tone: "neutral" as const, title: "尚未测试连接", detail: "可先测试，再保存并继续。" };
    }
    if (lastOk === true && busyIntent === null) {
      return {
        tone: "success" as const,
        title: "连接成功",
        detail: message || "连接测试成功（尚未保存配置）。",
      };
    }
    if (lastOk === false) {
      const needsRepair = /修复|repair|凭据/i.test(message);
      return {
        tone: "danger" as const,
        title: needsRepair ? "配置需要修复" : "连接失败",
        detail: message,
      };
    }
    return { tone: "neutral" as const, title: "尚未测试连接", detail: "" };
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
              <h3>欢迎使用 StoryLens</h3>
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
                  <p>适合快速完成章节和全书分析</p>
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
                  placeholder="已配置时可留空表示保持原凭据"
                  onChange={(e) => setApiKey(e.target.value)}
                />
                <small className="field-hint">
                  API Key 仅保存在 Windows 凭据管理器中。留空表示保持现有凭据不变。
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

              <label className="consent onboarding-consent-box">
                <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                <span>
                  为完成云端分析，所选章节正文会发送至阿里云百炼。
                  <em>正文不会进入 StoryLens 匿名使用统计。</em>
                </span>
              </label>

              <div
                className={`onboarding-status-card status-card onboarding-status-card--${connectionStatus.tone}`}
                role="status"
                data-testid="onboarding-connection-status"
              >
                <strong>{connectionStatus.title}</strong>
                {(message || busyIntent) && (
                  <p data-testid="onboarding-ai-message">{connectionStatus.detail || message}</p>
                )}
              </div>
              {setupSaved && (
                <p data-testid="onboarding-ai-saved" className="hint">
                  配置已保存，可用于分析。
                </p>
              )}
            </div>
          )}

          {step === 3 && (
            <div data-testid="onboarding-step-start" className="onboarding-done">
              <h3>{setupSaved ? "配置完成" : "可以开始使用"}</h3>
              {setupSaved ? (
                <ul className="onboarding-done-checklist">
                  <li>✓ AI 服务已连接</li>
                  <li>✓ 分析模式已设置</li>
                  <li>✓ 数据默认保存在本机</li>
                </ul>
              ) : (
                <p>导入第一本小说，或先浏览空书库；随时可在设置中修改 AI 配置。</p>
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
                <Button variant="ghost" onClick={() => setStep(3)}>
                  稍后配置
                </Button>
              </div>
              <div className="onboarding-footer-right">
                <Button
                  variant="secondary"
                  className="onboarding-btn-fixed"
                  disabled={busy}
                  onClick={() => void onTest()}
                  data-testid="onboarding-test"
                >
                  {busyIntent === "test" ? "测试中…" : "测试连接"}
                </Button>
                <Button
                  variant="primary"
                  className="onboarding-btn-fixed"
                  disabled={busy}
                  data-testid="onboarding-save-next"
                  onClick={() => void onSaveAndNext()}
                >
                  {busyIntent === "save" ? "保存中…" : "下一步"}
                </Button>
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
