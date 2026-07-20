import { useState } from "react";
import { useUiStore } from "../../stores/uiStore";
import { settingsApi } from "../../services/settingsApi";
import { useAdvancedSettingsStore } from "../../stores/advancedSettingsStore";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import "./settings.css";

export function SettingsAppearanceTab() {
  const ui = useUiStore();
  const showAdvanced = useAdvancedSettingsStore((s) => s.showAdvancedSettings);
  const setShowAdvanced = useAdvancedSettingsStore((s) => s.setShowAdvancedSettings);
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const setDeveloperMode = useDeveloperModeStore((s) => s.setDeveloperMode);
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
    <article className="settings-panel settings-module" data-testid="settings-panel-appearance">
      <header className="settings-panel-header">
        <h2>外观</h2>
        <p>阅读与界面偏好。调整后可在下方实时预览。</p>
      </header>

      <section className="settings-zone" data-testid="appearance-reading-zone">
        <h3>阅读</h3>
        <p className="zone-hint">正文字号与行距，影响阅读区排版。</p>
        <div className="settings-fields">
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
        </div>
      </section>

      <section className="settings-zone" data-testid="appearance-theme-zone">
        <h3>主题</h3>
        <p className="zone-hint">界面亮色 / 暗色。</p>
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
      </section>

      <section className="settings-zone" data-testid="appearance-ui-zone">
        <h3>界面选项</h3>
        <p className="zone-hint">高级与开发入口开关；不改变阅读存储键。</p>

        <label className="settings-switch-row" data-testid="show-advanced-settings">
          <span>
            <b>显示高级设置</b>
            <small>开启后可配置 Provider、Endpoint 与诊断项</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={showAdvanced}
            aria-label="显示高级设置"
            onChange={(e) => setShowAdvanced(e.target.checked)}
          />
        </label>

        {showAdvanced && (
          <>
            <label className="settings-switch-row" data-testid="developer-mode-in-settings">
              <span>
                <b>开发者模式</b>
                <small>显示任务、案例、模型与 API 等工程入口</small>
              </span>
              <input
                type="checkbox"
                role="switch"
                className="settings-switch"
                checked={developerMode}
                aria-label="开发者模式"
                onChange={(e) => setDeveloperMode(e.target.checked)}
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
          </>
        )}
      </section>

      <section className="settings-zone" data-testid="appearance-preview-zone">
        <h3>实时预览</h3>
        <div
          className="settings-appearance-preview"
          data-theme={ui.theme}
          data-testid="appearance-live-preview"
        >
          <p className="preview-label">阅读预览 · {ui.theme === "dark" ? "暗色" : "亮色"}</p>
          <p
            className="preview-prose"
            style={{ fontSize: `${ui.fontSize}px`, lineHeight: ui.lineHeight }}
          >
            夜色沉下来时，码头只剩下潮水拍打木桩的声音。他翻开那页旧笔记，字迹在灯火里微微发亮。
          </p>
        </div>
      </section>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button type="button" className="primary" disabled={saving} onClick={() => void save()}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </article>
  );
}
