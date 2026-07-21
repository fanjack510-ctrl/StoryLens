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
import { AboutAppVersion } from "./AboutAppVersion";
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
      setMessage(
        `已选择 ${channel} 通道（${endpointForChannel(channel)}）。若检查结果异常，请重启应用后重试。`,
      );
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
        setMessage("当前环境未启用自动更新检查（开发模式或桌面打包外）。");
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

  const showChannelPicker = prefs.internal_test_mode || developerMode;

  return (
    <div className="settings-module" data-testid="settings-panel-privacy">
      <article className="settings-card settings-panel" data-testid="settings-about-card">
        <header className="settings-panel-header">
          <h2>关于 StoryLens</h2>
          <p>应用版本来自统一 VERSION 源，与安装包 / updater 一致。</p>
        </header>
        <AboutAppVersion />
      </article>

      <article className="settings-card settings-panel" data-testid="settings-version-update-card">
        <header className="settings-panel-header">
          <h2>版本与更新</h2>
          <p>自动检查更新；下载与安装需你确认。不会静默安装，也不会删除用户数据。</p>
        </header>

        <dl className="settings-stat-grid" data-testid="settings-update-status-grid">
          <div className="settings-stat">
            <dt>当前版本</dt>
            <dd data-testid="settings-current-version">{snap.currentVersion || appVersion}</dd>
          </div>
          <div className="settings-stat">
            <dt>最新版本</dt>
            <dd data-testid="settings-latest-version">
              {snap.latestVersion || (snap.phase === "up_to_date" ? snap.currentVersion || appVersion : "—")}
            </dd>
          </div>
          <div className="settings-stat">
            <dt>更新状态</dt>
            <dd data-testid="settings-update-phase">{phaseLabel(snap.phase)}</dd>
          </div>
          <div className="settings-stat">
            <dt>上次检查</dt>
            <dd data-testid="settings-last-check-at">
              {formatCheckTime(snap.lastCheckAt || prefs.last_check_at)}
            </dd>
          </div>
        </dl>

        {updateAvailable && snap.latestVersion && (
          <p className="settings-update-available" data-testid="settings-update-available-banner" role="status">
            新版本 {snap.latestVersion} 可用
            {snap.phase === "dismissed" ? "（你曾选择稍后再说，仍可在此安装）" : ""}
          </p>
        )}

        <label className="settings-switch-row" data-testid="auto-check-update-switch">
          <span>
            <b>自动检查更新</b>
            <small>启动时仅检查，不自动下载或安装。</small>
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

        <p className="muted" data-testid="update-policy-note">
          自动下载与自动安装已关闭（正式默认）。远端清单不能开启静默安装。
        </p>

        {(developerMode || prefs.internal_test_mode) && (
          <label className="settings-switch-row" data-testid="internal-test-mode-switch">
            <span>
              <b>内部测试模式</b>
              <small>允许选择 staging 更新通道。普通用户请保持关闭。</small>
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
        )}

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

        <div className="settings-actions settings-update-actions">
          <button
            type="button"
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
            立即更新
          </button>

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
            下载后重启安装
          </button>

          {snap.phase === "downloaded" && (
            <button
              type="button"
              data-testid="settings-defer-install-button"
              disabled={busy}
              onClick={() => {
                deferInstall();
                setMessage("已保留下载包，可稍后安装。");
              }}
            >
              稍后安装
            </button>
          )}
        </div>

        {showNotes && (
          <div className="update-dialog-body" data-testid="settings-release-notes">
            <h3>更新说明</h3>
            <pre>{snap.releaseNotes || "暂无说明。"}</pre>
          </div>
        )}

        {message && <p role="status">{message}</p>}
        {snap.technicalDetail && snap.phase === "failed" && (
          <details>
            <summary>技术详情</summary>
            <pre data-testid="settings-update-technical">{snap.technicalDetail}</pre>
          </details>
        )}
      </article>

      <TelemetrySettingsCard />

      <UpdateAvailableDialog open={showDialog} onClose={() => setShowDialog(false)} />
    </div>
  );
}
