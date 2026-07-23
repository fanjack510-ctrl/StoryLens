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

  const densityValue =
    ui.lineHeight <= 1.5 ? "compact" : ui.lineHeight >= 2.1 ? "relaxed" : "normal";

  const setDensity = (value: string) => {
    const map: Record<string, number> = { compact: 1.4, normal: 1.9, relaxed: 2.3 };
    ui.setReading(ui.fontSize, map[value] ?? 1.9);
  };

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
        <p>调整阅读与界面显示。</p>
      </header>

      <section className="settings-zone" data-testid="appearance-theme-zone">
        <p className="hint" data-testid="appearance-theme-relocated-hint">
          界面主题可在页面右上角切换。
        </p>
      </section>

      <section className="settings-zone" data-testid="appearance-reading-zone">
        <label className="settings-field">
          <span>字体大小 · {ui.fontSize}px</span>
          <input
            type="range"
            min={14}
            max={26}
            value={ui.fontSize}
            aria-label="正文字号"
            onChange={(e) => ui.setReading(Number(e.target.value), ui.lineHeight)}
          />
          <small className="hint">影响阅读区正文字号。</small>
        </label>

        <label className="settings-field">
          <span>内容密度</span>
          <select
            value={densityValue}
            aria-label="内容密度"
            onChange={(e) => setDensity(e.target.value)}
          >
            <option value="compact">紧凑</option>
            <option value="normal">标准</option>
            <option value="relaxed">宽松</option>
          </select>
          <small className="hint">控制段落行距。</small>
        </label>

        <label className="settings-field">
          <span>阅读区域宽度</span>
          <select
            value={ui.contentWidth}
            aria-label="阅读区域宽度"
            onChange={(e) =>
              ui.setContentWidth(e.target.value as "narrow" | "normal" | "wide")
            }
          >
            <option value="narrow">较窄</option>
            <option value="normal">适中</option>
            <option value="wide">较宽</option>
          </select>
          <small className="hint">调整阅读栏宽度。</small>
        </label>
      </section>

      <section className="settings-zone" data-testid="appearance-preview-zone">
        <h3>预览</h3>
        <div
          className="settings-appearance-preview"
          data-theme={ui.theme}
          data-testid="appearance-live-preview"
        >
          <p className="preview-label">{ui.theme === "dark" ? "深色" : "浅色"}</p>
          <p
            className="preview-prose"
            style={{ fontSize: `${ui.fontSize}px`, lineHeight: ui.lineHeight }}
          >
            夜色沉下来时，码头只剩下潮水拍打木桩的声音。他翻开那页旧笔记，字迹在灯火里微微发亮。
          </p>
        </div>
      </section>

      <details
        className="settings-fold"
        data-testid="appearance-ui-zone"
        open={showAdvanced || developerMode}
      >
        <summary>高级界面选项</summary>
        <div className="settings-fold-body">
          <label className="settings-switch-row" data-testid="show-advanced-settings">
            <span>
              <b>显示开发者设置</b>
              <small>开启后可配置连接参数与诊断项</small>
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

          {(showAdvanced || developerMode) && (
            <>
              <label className="settings-switch-row" data-testid="developer-mode-in-settings">
                <span>
                  <b>开发者模式</b>
                  <small>显示工程入口</small>
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
                  <b>演示标记</b>
                  <small>不影响分析逻辑</small>
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
        </div>
      </details>

      {message && <p role="status">{message}</p>}
      <div className="settings-actions">
        <button type="button" className="primary" disabled={saving} onClick={() => void save()}>
          {saving ? "保存中…" : "保存"}
        </button>
      </div>
    </article>
  );
}
