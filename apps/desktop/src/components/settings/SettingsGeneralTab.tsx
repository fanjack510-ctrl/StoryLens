import { useState } from "react";
import { useUiStore } from "../../stores/uiStore";
import { settingsApi } from "../../services/settingsApi";

export function SettingsGeneralTab() {
  const ui = useUiStore();
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

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

  return (
    <article className="settings-panel" data-testid="settings-panel-general">
      <header className="settings-panel-header">
        <h2>通用</h2>
        <p>主题、阅读字号与演示模式。</p>
      </header>

      <div className="settings-fields">
        <label className="settings-field">
          <span>主题</span>
          <select
            value={ui.theme}
            onChange={(e) => ui.setTheme(e.target.value as "light" | "dark")}
            aria-label="主题"
          >
            <option value="light">亮色</option>
            <option value="dark">暗色</option>
          </select>
        </label>

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

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button type="button" className="primary" disabled={saving} onClick={save}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </article>
  );
}
