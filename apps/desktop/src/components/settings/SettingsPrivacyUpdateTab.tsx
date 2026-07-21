import { useState } from "react";
import { useAppVersion } from "../../lib/useAppVersion";
import { checkForAppUpdate } from "../../services/updaterService";
import { UpdateAvailableDialog } from "../desktop/UpdateAvailableDialog";
import { AboutAppVersion } from "./AboutAppVersion";
import { TelemetrySettingsCard } from "./TelemetrySettingsCard";
import "./settings.css";

export function SettingsPrivacyUpdateTab() {
  const appVersion = useAppVersion();
  const [message, setMessage] = useState("");
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [updateDialog, setUpdateDialog] = useState<{
    currentVersion: string;
    latestVersion: string;
    body: string;
    downloadAndInstall: () => Promise<void>;
  } | null>(null);

  const onCheckUpdate = async () => {
    setCheckingUpdate(true);
    setMessage("");
    try {
      const result = await checkForAppUpdate(true);
      if (result.kind === "disabled") {
        setMessage("当前环境未启用自动更新检查（开发模式或桌面打包外）。");
      } else if (result.kind === "latest") {
        setMessage(`当前已是最新版本（${result.currentVersion}）。`);
      } else if (result.kind === "available") {
        setUpdateDialog({
          currentVersion: result.currentVersion,
          latestVersion: result.latestVersion,
          body: result.body,
          downloadAndInstall: result.downloadAndInstall,
        });
      } else {
        setMessage(result.message);
      }
    } finally {
      setCheckingUpdate(false);
    }
  };

  return (
    <div className="settings-module" data-testid="settings-panel-privacy">
      <article className="settings-card settings-panel" data-testid="settings-about-card">
        <header className="settings-panel-header">
          <h2>关于 StoryLens</h2>
          <p>应用版本来自统一 VERSION 源，与安装包 / updater 一致。</p>
        </header>
        <AboutAppVersion />
      </article>

      <article className="settings-card settings-panel" data-testid="settings-update-card">
        <header className="settings-panel-header">
          <h2>自动更新</h2>
          <p>控制桌面版更新检查。开发模式或未打包环境可能无法检查。</p>
        </header>

        <label className="settings-switch-row" data-testid="auto-update-info">
          <span>
            <b>自动检查更新</b>
            <small>桌面版启动时会静默检查；此处可手动检查。</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked
            readOnly
            aria-label="自动检查更新说明"
          />
        </label>

        <p data-testid="settings-app-version">当前版本：{appVersion}</p>

        <div className="settings-actions">
          <button
            type="button"
            data-testid="check-update-button"
            disabled={checkingUpdate}
            onClick={() => void onCheckUpdate()}
          >
            {checkingUpdate ? "正在检查…" : "检查更新"}
          </button>
        </div>

        {message && <p role="status">{message}</p>}

        {updateDialog && (
          <UpdateAvailableDialog
            currentVersion={updateDialog.currentVersion}
            latestVersion={updateDialog.latestVersion}
            body={updateDialog.body}
            onLater={() => setUpdateDialog(null)}
            onUpdate={async () => {
              try {
                await updateDialog.downloadAndInstall();
              } catch {
                setMessage("更新安装失败。这不影响本地分析，请稍后重试。");
                setUpdateDialog(null);
              }
            }}
          />
        )}
      </article>

      <TelemetrySettingsCard />
    </div>
  );
}
