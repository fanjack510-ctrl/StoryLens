import { useEffect, useState } from "react";
import { useTelemetryStore } from "../../stores/telemetry";
import "./settings.css";

const PRIVACY_DOC_PATH = "docs/telemetry-plan.md";

function maskInstallId(id: string | null): string {
  if (!id) return "尚未生成（启用统计或重置后会创建）";
  if (id.length <= 8) return `${id.slice(0, 2)}…`;
  return `${id.slice(0, 4)}…${id.slice(-4)}`;
}

function consentLabel(consent: string): { text: string; tone: "neutral" | "success" | "warning" } {
  if (consent === "ENABLED") return { text: "已启用（ENABLED）", tone: "success" };
  if (consent === "DISABLED") return { text: "已关闭（DISABLED）", tone: "neutral" };
  return { text: "尚未选择（UNKNOWN）", tone: "warning" };
}

export function TelemetrySettingsCard() {
  const consent = useTelemetryStore((s) => s.consent);
  const installIdPreview = useTelemetryStore((s) => s.installIdPreview);
  const setEnabled = useTelemetryStore((s) => s.setAnonymousTelemetryEnabled);
  const resetId = useTelemetryStore((s) => s.resetAnonymousInstallId);
  const refreshPreview = useTelemetryStore((s) => s.refreshInstallIdPreview);
  const [message, setMessage] = useState("");

  useEffect(() => {
    refreshPreview();
  }, [refreshPreview]);

  const enabled = consent === "ENABLED";
  const status = consentLabel(consent);

  const onToggle = (next: boolean) => {
    setMessage("");
    setEnabled(next);
    if (next) {
      refreshPreview();
      setMessage("已启用匿名使用统计。你可以随时在此关闭。");
    } else {
      setMessage("已关闭匿名使用统计，不会再发送新事件。");
    }
  };

  const onResetId = () => {
    resetId();
    setMessage("已重置匿名安装 ID。此前 ID 与后续事件无法关联。");
  };

  return (
    <article className="settings-card settings-panel" data-testid="telemetry-settings-card">
      <header className="settings-panel-header">
        <h2>匿名使用统计</h2>
        <p>可选、默认关闭。仅在你明确同意后才会发送汇总使用情况。</p>
      </header>

      <p data-testid="telemetry-consent-status">
        <span className="settings-status-pill" data-tone={status.tone}>
          {status.text}
        </span>
      </p>

      <div className="settings-fields">
        <label className="settings-switch-row" data-testid="telemetry-consent-switch">
          <span>
            <b>允许匿名使用统计</b>
            <small>
              {consent === "UNKNOWN"
                ? "尚未选择；关闭状态下不会发送任何数据"
                : enabled
                  ? "已启用"
                  : "已明确关闭"}
            </small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={enabled}
            aria-label="允许匿名使用统计"
            onChange={(e) => onToggle(e.target.checked)}
          />
        </label>

        <div className="privacy-note" data-testid="telemetry-collected-summary">
          <h3>可能收集的内容</h3>
          <ul>
            <li>应用版本、操作系统族、界面语言</li>
            <li>功能使用次数（如开始/完成分析、更新安装）</li>
            <li>匿名随机安装 ID（非账号、非设备指纹）</li>
          </ul>
        </div>

        <div className="privacy-note" data-testid="telemetry-not-collected">
          <h3>不会收集</h3>
          <ul>
            <li>书名、章节标题、段落或任何小说正文</li>
            <li>文件路径、API Key、提示词或完整错误堆栈</li>
            <li>用户名、机器名或可用于精确识别设备的指纹</li>
          </ul>
        </div>

        <div className="settings-field" data-testid="telemetry-install-id">
          <span>匿名安装 ID（摘要）</span>
          <output aria-live="polite">{maskInstallId(installIdPreview)}</output>
        </div>

        <div className="settings-actions">
          <button type="button" onClick={onResetId} data-testid="telemetry-reset-install-id">
            重置匿名安装 ID
          </button>
        </div>

        <p className="muted" data-testid="telemetry-privacy-link">
          隐私说明见项目文档{" "}
          <a href={`/${PRIVACY_DOC_PATH}`} rel="noopener noreferrer">
            {PRIVACY_DOC_PATH}
          </a>
          与 <code>docs/privacy.md</code>。
        </p>
      </div>

      {message ? <p role="status">{message}</p> : null}
    </article>
  );
}
