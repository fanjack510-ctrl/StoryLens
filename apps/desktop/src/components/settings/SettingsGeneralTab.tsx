import { useState } from "react";
import { useUiStore } from "../../stores/uiStore";
import { settingsApi } from "../../services/settingsApi";
import { checkForAppUpdate } from "../../services/updaterService";
import { UpdateAvailableDialog } from "../desktop/UpdateAvailableDialog";

/**
 * Legacy general tab (appearance + update). SettingsPage maps "general" → appearance;
 * update entry lives under 隐私与更新. Kept for deep-links / tests.
 */
export function SettingsGeneralTab() {
  const ui = useUiStore();
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [showDialog, setShowDialog] = useState(false);

  const save = async () => {
    setSaving(true);
    setMessage("");
    try {
      await settingsApi.save({
        demo_mode: ui.demo,
        theme: ui.theme,
        font_size: ui.fontSize,
        line_height: ui.lineHeight,
      });
      setMessage("外观设置已保存。");
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setSaving(false);
    }
  };

  const onCheckUpdate = async () => {
    setCheckingUpdate(true);
    setMessage("");
    try {
      const result = await checkForAppUpdate(true);
      if (result.kind === "disabled") {
        setMessage("当前环境未启用自动更新检查（开发模式或已关闭）。");
      } else if (result.kind === "latest") {
        setMessage(`当前已是最新版本（${result.currentVersion}）。`);
      } else if (result.kind === "available") {
        setShowDialog(true);
        setMessage(`新版本 ${result.latestVersion} 可用。`);
      } else {
        setMessage(result.message);
      }
    } finally {
      setCheckingUpdate(false);
    }
  };

  return (
    <article className="settings-panel" data-testid="settings-panel-general">
      <header className="settings-panel-header">
        <h2>通用</h2>
        <p>主题、阅读字号与演示模式。</p>
      </header>

      <div className="settings-fields">
        <p className="hint" data-testid="appearance-theme-relocated-hint">
          界面主题可在页面右上角切换。
        </p>

        <label className="settings-field">
          <span>正文字号 · {ui.fontSize}px</span>
          <input
            type="range"
            min={14}
            max={26}
            value={ui.fontSize}
            aria-label="正文字号"
            onChange={(e) => ui.setReading(Number(e.target.value), ui.lineHeight)}
          />
        </label>

        <label className="settings-field">
          <span>行距 · {ui.lineHeight}</span>
          <input
            type="range"
            min={1.3}
            max={2.6}
            step={0.1}
            value={ui.lineHeight}
            aria-label="行距"
            onChange={(e) => ui.setReading(ui.fontSize, Number(e.target.value))}
          />
        </label>

        <label className="settings-switch-row" data-testid="demo-mode-switch">
          <span>
            <b>Demo 模式</b>
            <small>演示环境标记，不影响分析逻辑</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={ui.demo}
            aria-label="Demo 模式"
            onChange={(e) => ui.setDemo(e.target.checked)}
          />
        </label>
      </div>

      <section className="settings-update-block" data-testid="settings-update-block">
        <h3>软件更新</h3>
        <p>检查是否有新版本。检查失败不会影响本地分析。下载与安装需确认。</p>
        <button
          type="button"
          data-testid="check-update-button"
          disabled={checkingUpdate}
          onClick={() => void onCheckUpdate()}
        >
          {checkingUpdate ? "正在检查…" : "检查更新"}
        </button>
      </section>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button type="button" className="primary" disabled={saving} onClick={save}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>

      <UpdateAvailableDialog open={showDialog} onClose={() => setShowDialog(false)} />
    </article>
  );
}
