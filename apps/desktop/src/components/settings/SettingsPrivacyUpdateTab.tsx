import { useEffect, useState } from "react";
import { useAppVersion } from "../../lib/useAppVersion";
import { useDeveloperModeStore } from "../../stores/developerModeStore";
import {
  checkForAppUpdate,
  confirmInstall,
  deferInstall,
  endpointForChannel,
  getUpdaterSnapshot,
  loadUpdaterPreferences,
  patchUpdaterPreferences,
  relaunchToApplyUpdate,
  startDownload,
  subscribeUpdater,
  type UpdateChannel,
  type UpdaterSnapshot,
} from "../../services/updaterService";
import { phaseLabel } from "../../services/updater/types";
import { UpdateAvailableDialog } from "../desktop/UpdateAvailableDialog";
import { TelemetrySettingsCard } from "./TelemetrySettingsCard";
import "./settings.css";

function formatCheckTime(iso: string | null): string {
  if (!iso) return "尚未检查";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return iso;
  try {
    return new Date(t).toLocaleString();
  } catch {
    return iso;
  }
}

function updateStatusLabel(snap: UpdaterSnapshot, appVersion: string): string {
  if (snap.phase === "failed") return "检查失败";
  if (snap.phase === "up_to_date") return "已是最新版本";
  if (
    snap.latestVersion &&
    snap.latestVersion !== (snap.currentVersion || appVersion) &&
    snap.phase !== "idle"
  ) {
    return "有新版本可用";
  }
  if (!snap.lastCheckAt) return "尚未检查";
  if (snap.phase === "idle") return "尚未检查";
  return phaseLabel(snap.phase);
}

export function SettingsPrivacyUpdateTab() {
  const appVersion = useAppVersion();
  const developerMode = useDeveloperModeStore((s) => s.developerMode);
  const [prefs, setPrefs] = useState(() => loadUpdaterPreferences());
  const [snap, setSnap] = useState<UpdaterSnapshot>(() => getUpdaterSnapshot());
  const [message, setMessage] = useState("");
  const [checkingUpdate, setCheckingUpdate] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [showDialog, setShowDialog] = useState(false);

  useEffect(() => subscribeUpdater(setSnap), []);

  const refreshPrefs = () => setPrefs(loadUpdaterPreferences());

  const onToggleAutoCheck = (checked: boolean) => {
    const next = patchUpdaterPreferences({ automatic_check: checked });
    setPrefs(next);
  };

  const onToggleInternalTest = (checked: boolean) => {
    const next = patchUpdaterPreferences({
      internal_test_mode: checked,
      channel: checked ? prefs.channel : "stable",
    });
    setPrefs(next);
    if (checked) {
      setMessage("内部测试模式已开启。切换更新通道后建议重启应用再检查。");
    } else {
      setMessage("已退出内部测试模式，更新通道固定为 stable。");
    }
  };

  const onChannelChange = async (channel: UpdateChannel) => {
    if (!prefs.internal_test_mode && !developerMode) return;
    const next = patchUpdaterPreferences({ channel, internal_test_mode: true });
    setPrefs(next);
    try {
      if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
        const { invoke } = await import("@tauri-apps/api/core");
        await invoke("set_updater_channel", { channel });
      }
      setMessage(`已选择 ${channel} 通道。若检查结果异常，请重启应用后重试。`);
    } catch (error) {
      setMessage(
        `通道已保存在本地；同步到桌面运行时失败：${
          error instanceof Error ? error.message : String(error)
        }`,
      );
    }
  };

  const onCheckUpdate = async () => {
    setCheckingUpdate(true);
    setMessage("");
    try {
      const result = await checkForAppUpdate(true);
      refreshPrefs();
      if (result.kind === "disabled") {
        setMessage("当前环境未启用自动更新检查。");
      } else if (result.kind === "latest") {
        setMessage(`当前已是最新版本（${result.currentVersion}）。`);
      } else if (result.kind === "available") {
        setMessage(`新版本 ${result.latestVersion} 可用。`);
        setShowDialog(true);
      } else {
        setMessage(result.message);
      }
    } finally {
      setCheckingUpdate(false);
    }
  };

  const onStartDownload = async () => {
    setBusy(true);
    setMessage("");
    try {
      const next = await startDownload();
      if (next.phase === "downloaded") {
        setMessage("更新包已下载。可稍后安装，或立即重启并安装。");
        setShowDialog(true);
      } else if (next.phase === "failed") {
        setMessage(next.message);
        setShowDialog(true);
      }
    } finally {
      setBusy(false);
    }
  };

  const onInstall = async () => {
    setBusy(true);
    try {
      const next = await confirmInstall();
      if (next.phase === "restart_required") {
        setMessage("更新已安装。请保存工作后重启。");
        setShowDialog(true);
      } else if (next.phase === "failed") {
        setMessage(next.message);
      }
    } finally {
      setBusy(false);
    }
  };

  const updateAvailable =
    Boolean(snap.latestVersion) &&
    snap.latestVersion !== snap.currentVersion &&
    (snap.phase === "available" ||
      snap.phase === "dismissed" ||
      snap.phase === "downloaded" ||
      snap.phase === "restart_required" ||
      snap.phase === "failed" ||
      snap.phase === "downloading");

  const showChannelPicker = developerMode && (prefs.internal_test_mode || developerMode);
  const statusText = updateStatusLabel(snap, appVersion);

  return (
    <div className="settings-module" data-testid="settings-panel-privacy">
      <article className="settings-card settings-panel" data-testid="settings-version-update-card">
        <header className="settings-panel-header">
          <h2>软件更新</h2>
        </header>

        <p className="settings-status-line" data-testid="settings-current-version">
          当前版本：{snap.currentVersion || appVersion}
        </p>
        <p className="settings-status-reason" data-testid="settings-update-phase">
          {statusText}
        </p>

        {/* Keep latest version node for tests / screen readers without equal visual weight */}
        <span className="visually-hidden" data-testid="settings-latest-version">
          {snap.latestVersion || (snap.phase === "up_to_date" ? snap.currentVersion || appVersion : "—")}
        </span>
        <span className="visually-hidden" data-testid="settings-last-check-at">
          {formatCheckTime(snap.lastCheckAt || prefs.last_check_at)}
        </span>
        <span className="visually-hidden" data-testid="settings-update-status-grid" />

        {updateAvailable && snap.latestVersion && (
          <p className="settings-update-available" data-testid="settings-update-available-banner" role="status">
            新版本 {snap.latestVersion} 可用
          </p>
        )}

        <label className="settings-switch-row" data-testid="auto-check-update-switch">
          <span>
            <b>自动检查更新</b>
            <small>启动时仅检查，不会自动安装。</small>
          </span>
          <input
            type="checkbox"
            role="switch"
            className="settings-switch"
            checked={prefs.automatic_check}
            aria-label="自动检查更新"
            onChange={(e) => onToggleAutoCheck(e.target.checked)}
          />
        </label>

        <div className="settings-actions settings-update-actions">
          <button
            type="button"
            className="primary"
            data-testid="check-update-button"
            disabled={checkingUpdate || busy}
            onClick={() => void onCheckUpdate()}
          >
            {checkingUpdate ? "正在检查…" : "检查更新"}
          </button>

          <button
            type="button"
            data-testid="view-release-notes-button"
            disabled={!snap.releaseNotes && !snap.latestVersion}
            onClick={() => setShowNotes((v) => !v)}
          >
            查看更新说明
          </button>

          {updateAvailable && (
            <>
              <button
                type="button"
                className="primary"
                data-testid="settings-start-download-button"
                disabled={
                  busy ||
                  !snap.latestVersion ||
                  snap.phase === "downloading" ||
                  snap.phase === "installing" ||
                  snap.phase === "up_to_date" ||
                  snap.phase === "idle"
                }
                onClick={() => void onStartDownload()}
              >
                下载更新
              </button>
              <button
                type="button"
                data-testid="settings-defer-install-button"
                disabled={busy}
                onClick={() => {
                  deferInstall();
                  setMessage("已稍后处理，可随时回来继续。");
                }}
              >
                稍后处理
              </button>
            </>
          )}

          {!updateAvailable && (
            <button
              type="button"
              className="visually-hidden"
              tabIndex={-1}
              data-testid="settings-start-download-button"
              disabled
            >
              下载更新
            </button>
          )}

          <button
            type="button"
            data-testid="settings-install-relaunch-button"
            disabled={busy || (snap.phase !== "downloaded" && snap.phase !== "restart_required")}
            onClick={() => {
              if (snap.phase === "downloaded") {
                void onInstall();
              } else {
                void relaunchToApplyUpdate().catch((error) => {
                  setMessage(error instanceof Error ? error.message : String(error));
                });
              }
            }}
          >
            重启并安装
          </button>
        </div>

        {showNotes && (
          <div className="update-dialog-body" data-testid="settings-release-notes">
            <h3>更新说明</h3>
            <pre>{snap.releaseNotes || "暂无说明。"}</pre>
          </div>
        )}

        {message && <p role="status">{message}</p>}

        {developerMode && (
          <details className="settings-fold" data-testid="update-advanced-fold">
            <summary>更新高级设置</summary>
            <div className="settings-fold-body">
              <label className="settings-switch-row" data-testid="internal-test-mode-switch">
                <span>
                  <b>内部测试模式</b>
                  <small>仅开发者使用。</small>
                </span>
                <input
                  type="checkbox"
                  role="switch"
                  className="settings-switch"
                  checked={prefs.internal_test_mode}
                  aria-label="内部测试模式"
                  onChange={(e) => onToggleInternalTest(e.target.checked)}
                />
              </label>
              {showChannelPicker && (
                <label className="settings-field" data-testid="update-channel-select">
                  <span>更新通道</span>
                  <select
                    value={prefs.channel}
                    aria-label="更新通道"
                    onChange={(e) => void onChannelChange(e.target.value as UpdateChannel)}
                  >
                    <option value="stable">stable（正式）</option>
                    <option value="staging">staging（内部测试）</option>
                  </select>
                  <small className="muted">{endpointForChannel(prefs.channel)}</small>
                </label>
              )}
              {!showChannelPicker && (
                <p className="muted" data-testid="update-channel-stable-only">
                  更新通道：stable
                </p>
              )}
              {snap.technicalDetail && snap.phase === "failed" && (
                <details>
                  <summary>技术详情</summary>
                  <pre data-testid="settings-update-technical">{snap.technicalDetail}</pre>
                </details>
              )}
            </div>
          </details>
        )}
      </article>

      <TelemetrySettingsCard />

      <UpdateAvailableDialog open={showDialog} onClose={() => setShowDialog(false)} />
    </div>
  );
}
