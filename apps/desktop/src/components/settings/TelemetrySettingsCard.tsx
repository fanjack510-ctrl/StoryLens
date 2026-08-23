import { useEffect, useState } from "react";
import { useTelemetryStore } from "../../stores/telemetry";
import "./settings.css";

function maskInstallId(id: string | null): string {
  if (!id) return "尚未生成";
  if (id.length <= 8) return `${id.slice(0, 2)}…`;
  return `${id.slice(0, 4)}…${id.slice(-4)}`;
}

export function TelemetrySettingsCard() {
  const consent = useTelemetryStore((s) => s.consent);
  const installIdPreview = useTelemetryStore((s) => s.installIdPreview);
  const setEnabled = useTelemetryStore((s) => s.setAnonymousTelemetryEnabled);
  const resetId = useTelemetryStore((s) => s.resetAnonymousInstallId);
  const refreshPreview = useTelemetryStore((s) => s.refreshInstallIdPreview);
  const [message, setMessage] = useState("");
  const [showCollected, setShowCollected] = useState(false);

  useEffect(() => {
    refreshPreview();
  }, [refreshPreview]);

  const enabled = consent === "ENABLED";

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
    setMessage("已重置匿名安装 ID。");
  };

  return (
    <article className="settings-card settings-panel" data-testid="telemetry-settings-card">
      <header className="settings-panel-header">
        <h2>帮助改进StoryLens</h2>
        <p>
          允许发送匿名的应用版本、系统类型和功能使用次数。不会收集书籍正文、API Key或个人身份信息。
        </p>
      </header>

      <p className="visually-hidden" data-testid="telemetry-consent-status">
        {consent === "ENABLED" ? "已启用" : consent === "DISABLED" ? "已关闭" : "尚未选择"}
      </p>

      <div className="settings-fields">
        <label className="settings-switch-row" data-testid="telemetry-consent-switch">
          <span>
            <b>发送匿名使用统计</b>
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

        <button
          type="button"
          className="linkish"
          data-testid="telemetry-privacy-link"
          onClick={() => setShowCollected((v) => !v)}
        >
          {showCollected ? "收起收集内容" : "查看收集内容"}
        </button>

        {showCollected && (
          <div className="settings-fold-body">
            <div className="privacy-note" data-testid="telemetry-collected-summary">
              <h3>收集</h3>
              <ul>
                <li>应用版本</li>
                <li>操作系统类型</li>
                <li>界面语言</li>
                <li>匿名功能使用次数</li>
              </ul>
            </div>
            <div className="privacy-note" data-testid="telemetry-not-collected">
              <h3>不收集</h3>
              <ul>
                <li>书籍正文</li>
                <li>分析结果</li>
                <li>文件路径</li>
                <li>API Key</li>
                <li>用户名</li>
                <li>设备硬件指纹</li>
              </ul>
            </div>
          </div>
        )}
              </div>

      {message && (
        <p role="status" data-testid="telemetry-message">
          {message}
        </p>
      )}
    </article>
  );
}
