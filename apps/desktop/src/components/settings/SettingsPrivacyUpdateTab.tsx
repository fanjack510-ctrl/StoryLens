import { useState } from "react";
import { checkForAppUpdate } from "../../services/updaterService";
import { UpdateAvailableDialog } from "../desktop/UpdateAvailableDialog";

const APP_VERSION = "1.0.0-rc1";

export function SettingsPrivacyUpdateTab() {
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
    <article className="settings-panel" data-testid="settings-panel-privacy">
      <header className="settings-panel-header">
        <h2>隐私与更新</h2>
        <p>控制更新检查与了解数据如何使用。</p>
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

      <label className="settings-switch-row" data-testid="telemetry-placeholder">
        <span>
          <b>匿名使用统计</b>
          <small>尚未启用 · 不会发送网络请求</small>
        </span>
        <input
          type="checkbox"
          role="switch"
          className="settings-switch"
          disabled
          aria-label="匿名使用统计"
        />
      </label>

      <p className="hint">
        <a href="https://storylens.app/privacy" target="_blank" rel="noreferrer">
          查看隐私说明
        </a>
        （占位链接，正式版将替换为有效地址）
      </p>

      <p data-testid="settings-app-version">当前版本：{APP_VERSION}</p>

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
  );
}
