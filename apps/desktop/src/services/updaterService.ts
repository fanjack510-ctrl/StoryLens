import { BUILD_APP_VERSION, formatAppVersionLabel } from "../lib/appVersion";
import {
  endpointForChannel,
  normalizeUpdateChannel,
  type UpdateChannel,
} from "./updater/channels";
import {
  loadUpdaterPreferences,
  markUpdateDismissed,
  patchUpdaterPreferences,
  shouldShowUpdateDialog,
  type UpdaterPreferences,
} from "./updater/preferences";
import {
  INITIAL_UPDATER_SNAPSHOT,
  type DownloadProgress,
  type UpdaterPhase,
  type UpdaterSnapshot,
} from "./updater/types";

export type { UpdateChannel, UpdaterPreferences, UpdaterPhase, UpdaterSnapshot, DownloadProgress };
export {
  endpointForChannel,
  loadUpdaterPreferences,
  patchUpdaterPreferences,
  shouldShowUpdateDialog,
  markUpdateDismissed,
};

/** @deprecated Prefer UpdaterSnapshot + controller; kept for gradual migration. */
export type UpdateCheckResult =
  | { kind: "disabled" }
  | { kind: "latest"; currentVersion: string }
  | {
      kind: "available";
      currentVersion: string;
      latestVersion: string;
      body: string;
      /** @deprecated Use startDownload / confirmInstall — never auto-installs. */
      downloadAndInstall: () => Promise<void>;
    }
  | { kind: "error"; message: string };

type TauriUpdate = {
  version: string;
  currentVersion: string;
  body?: string;
  download: (
    onEvent?: (event: {
      event: string;
      data: { contentLength?: number; chunkLength?: number };
    }) => void,
  ) => Promise<void>;
  install: () => Promise<void>;
  close: () => Promise<void>;
};

type Listener = (snapshot: UpdaterSnapshot) => void;

let snapshot: UpdaterSnapshot = { ...INITIAL_UPDATER_SNAPSHOT };
let pendingUpdate: TauriUpdate | null = null;
const listeners = new Set<Listener>();

function emit(): void {
  const frozen = { ...snapshot, progress: snapshot.progress ? { ...snapshot.progress } : null };
  for (const listener of listeners) {
    listener(frozen);
  }
}

function setSnapshot(patch: Partial<UpdaterSnapshot>): void {
  snapshot = { ...snapshot, ...patch };
  emit();
}

export function getUpdaterSnapshot(): UpdaterSnapshot {
  return {
    ...snapshot,
    progress: snapshot.progress ? { ...snapshot.progress } : null,
  };
}

export function subscribeUpdater(listener: Listener): () => void {
  listeners.add(listener);
  listener(getUpdaterSnapshot());
  return () => {
    listeners.delete(listener);
  };
}

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function userFacingError(detail: string): string {
  if (/signature|sign|验签|minisign/i.test(detail)) {
    return "更新包签名校验失败，已禁止安装。这不影响本地分析与已有数据。";
  }
  if (/network|fetch|timeout|Failed to fetch|连接|ECONN|ENOTFOUND/i.test(detail)) {
    return "网络异常，更新检查或下载失败。请稍后重试。";
  }
  return "更新失败。这不影响本地分析与已有数据，请稍后重试。";
}

async function resolveCurrentVersion(): Promise<string> {
  if (isTauriRuntime()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const runtime = await invoke<string>("get_app_version");
      if (typeof runtime === "string" && runtime.trim()) {
        return formatAppVersionLabel(runtime.trim());
      }
    } catch {
      /* fall through */
    }
  }
  return formatAppVersionLabel(BUILD_APP_VERSION);
}

async function clearPendingUpdate(): Promise<void> {
  if (!pendingUpdate) return;
  try {
    await pendingUpdate.close();
  } catch {
    /* ignore */
  }
  pendingUpdate = null;
}

/**
 * Policy helpers — used by tests and release guards.
 * Checking must never download or install.
 */
export function assertCheckDoesNotDownloadOrInstall(prefs: UpdaterPreferences = loadUpdaterPreferences()): void {
  if (prefs.automatic_download) {
    throw new Error("automatic_download must be false");
  }
  if (prefs.automatic_install) {
    throw new Error("automatic_install must be false");
  }
}

export function defaultUpdaterPolicy(): Pick<
  UpdaterPreferences,
  "automatic_check" | "automatic_download" | "automatic_install" | "channel"
> {
  return {
    automatic_check: true,
    automatic_download: false,
    automatic_install: false,
    channel: "stable",
  };
}

async function createUpdateFromCheck(channel: UpdateChannel): Promise<TauriUpdate | null> {
  const { invoke } = await import("@tauri-apps/api/core");
  const enabled = await invoke<boolean>("updater_enabled");
  if (!enabled) {
    return null;
  }

  // Prefer channel-aware Rust command (staging / stable isolation).
  try {
    const metadata = await invoke<{
      rid: number;
      currentVersion: string;
      version: string;
      date?: string;
      body?: string;
      rawJson: Record<string, unknown>;
    } | null>("storylens_updater_check", { channel });

    if (!metadata) {
      return null;
    }
    const { Update } = await import("@tauri-apps/plugin-updater");
    return new Update(metadata) as unknown as TauriUpdate;
  } catch {
    // Fallback to plugin check (stable endpoint from tauri.conf).
    const { check } = await import("@tauri-apps/plugin-updater");
    const update = await check();
    return update as unknown as TauriUpdate | null;
  }
}

/**
 * Check only — never downloads, never installs, never relaunches.
 */
export async function checkForAppUpdate(manual = false): Promise<UpdateCheckResult> {
  assertCheckDoesNotDownloadOrInstall();

  if (
    typeof sessionStorage !== "undefined" &&
    sessionStorage.getItem("storylens.uiAudit") === "1" &&
    manual
  ) {
    const currentVersion = formatAppVersionLabel(BUILD_APP_VERSION);
    const latestVersion = `${currentVersion}-audit`;
    setSnapshot({
      phase: "available",
      currentVersion,
      latestVersion,
      releaseNotes: "审计模拟更新说明：稳定性修复与界面安全基线。",
      message: `发现新版本 ${latestVersion}`,
      technicalDetail: null,
      progress: null,
      lastCheckAt: new Date().toISOString(),
      channel: "stable",
    });
    return {
      kind: "available",
      currentVersion,
      latestVersion,
      body: "审计模拟更新说明：稳定性修复与界面安全基线。",
      downloadAndInstall: async () => {
        throw new Error("审计模式禁止自动下载安装；请使用 startDownload / confirmInstall。");
      },
    };
  }

  const prefs = loadUpdaterPreferences();
  const channel = prefs.internal_test_mode ? normalizeUpdateChannel(prefs.channel) : "stable";

  if (!manual && !prefs.automatic_check) {
    setSnapshot({
      phase: "idle",
      message: "已关闭自动检查更新",
      channel,
    });
    return { kind: "disabled" };
  }

  if (!isTauriRuntime()) {
    setSnapshot({ phase: "idle", message: "当前环境未启用桌面更新", channel });
    return { kind: "disabled" };
  }

  setSnapshot({
    phase: "checking",
    message: "正在检查更新…",
    technicalDetail: null,
    progress: null,
    channel,
  });

  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const enabled = await invoke<boolean>("updater_enabled");
    if (!enabled) {
      setSnapshot({ phase: "idle", message: "开发模式未启用更新检查", channel });
      return { kind: "disabled" };
    }

    await clearPendingUpdate();
    const update = await createUpdateFromCheck(channel);
    const currentVersion = update?.currentVersion
      ? formatAppVersionLabel(update.currentVersion)
      : await resolveCurrentVersion();
    const checkedAt = new Date().toISOString();
    patchUpdaterPreferences({ last_check_at: checkedAt });

    if (!update) {
      setSnapshot({
        phase: "up_to_date",
        currentVersion,
        latestVersion: currentVersion,
        releaseNotes: "",
        message: `当前已是最新版本（${currentVersion}）`,
        technicalDetail: null,
        progress: null,
        lastCheckAt: checkedAt,
        channel,
      });
      return { kind: "latest", currentVersion };
    }

    pendingUpdate = update;
    const latestVersion = update.version;
    const body = update.body || "修复问题并改进稳定性。";
    const prefsAfter = loadUpdaterPreferences();
    const dismissedQuiet =
      !manual && !shouldShowUpdateDialog(prefsAfter, latestVersion);

    setSnapshot({
      phase: dismissedQuiet ? "dismissed" : "available",
      currentVersion,
      latestVersion,
      releaseNotes: body,
      message: `发现新版本 ${latestVersion}`,
      technicalDetail: null,
      progress: null,
      lastCheckAt: checkedAt,
      channel,
    });

    return {
      kind: "available",
      currentVersion,
      latestVersion,
      body,
      downloadAndInstall: async () => {
        // Hard block legacy one-shot path — must go through opt-in steps.
        throw new Error(
          "自动下载安装已禁用。请先确认下载，下载完成后再确认安装。",
        );
      },
    };
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    if (!manual) {
      console.warn("update check failed (ignored):", detail);
      setSnapshot({
        phase: "idle",
        message: "",
        technicalDetail: detail,
        channel,
      });
      return { kind: "disabled" };
    }
    setSnapshot({
      phase: "failed",
      message: userFacingError(detail),
      technicalDetail: detail,
      progress: null,
      channel,
    });
    return {
      kind: "error",
      message: "检查更新失败。这不影响本地分析，请稍后重试或检查网络。",
    };
  }
}

/** User clicked 稍后再说 — no network download. */
export function dismissAvailableUpdate(): UpdaterSnapshot {
  const latest = snapshot.latestVersion;
  if (latest) {
    markUpdateDismissed(latest);
  }
  setSnapshot({
    phase: "dismissed",
    message: latest ? `新版本 ${latest} 可用（已稍后提醒）` : "已稍后提醒",
    progress: null,
  });
  return getUpdaterSnapshot();
}

/**
 * User clicked 立即更新 — download only.
 * Does not install, does not relaunch, does not exit the app.
 */
export async function startDownload(): Promise<UpdaterSnapshot> {
  assertCheckDoesNotDownloadOrInstall();
  const prefs = loadUpdaterPreferences();
  if (prefs.automatic_download) {
    setSnapshot({
      phase: "failed",
      message: "安全策略禁止自动下载。",
      technicalDetail: "automatic_download=true is not allowed",
    });
    return getUpdaterSnapshot();
  }

  if (!pendingUpdate && snapshot.latestVersion?.endsWith("-audit")) {
    setSnapshot({
      phase: "downloaded",
      message: "审计模拟：更新包已下载，等待确认安装。",
      progress: { downloadedBytes: 1, totalBytes: 1, percent: 100 },
    });
    return getUpdaterSnapshot();
  }

  if (!pendingUpdate) {
    setSnapshot({
      phase: "failed",
      message: "没有可下载的更新，请先检查更新。",
      technicalDetail: "pendingUpdate is null",
    });
    return getUpdaterSnapshot();
  }

  setSnapshot({
    phase: "downloading",
    message: "正在下载更新…",
    technicalDetail: null,
    progress: { downloadedBytes: 0, totalBytes: null, percent: null },
  });

  let downloaded = 0;
  let total: number | null = null;

  try {
    await pendingUpdate.download((event) => {
      if (event.event === "Started") {
        total = event.data.contentLength ?? null;
        downloaded = 0;
      } else if (event.event === "Progress") {
        downloaded += event.data.chunkLength ?? 0;
      } else if (event.event === "Finished") {
        /* keep totals */
      }
      const percent =
        total && total > 0 ? Math.min(100, Math.round((downloaded / total) * 100)) : null;
      const progress: DownloadProgress = {
        downloadedBytes: downloaded,
        totalBytes: total,
        percent,
      };
      setSnapshot({
        phase: "downloading",
        progress,
        message: percent != null ? `正在下载更新… ${percent}%` : "正在下载更新…",
      });
    });

    setSnapshot({
      phase: "downloaded",
      message: "更新包已下载。请确认后再安装；安装前请保存正在编辑的内容。",
      progress: {
        downloadedBytes: downloaded,
        totalBytes: total,
        percent: 100,
      },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setSnapshot({
      phase: "failed",
      message: userFacingError(detail),
      technicalDetail: detail,
      progress: null,
    });
  }

  return getUpdaterSnapshot();
}

/**
 * User confirmed install — install only.
 * Does not relaunch until the caller asks (restart_required).
 */
export async function confirmInstall(): Promise<UpdaterSnapshot> {
  assertCheckDoesNotDownloadOrInstall();
  const prefs = loadUpdaterPreferences();
  if (prefs.automatic_install) {
    setSnapshot({
      phase: "failed",
      message: "安全策略禁止自动安装。",
      technicalDetail: "automatic_install=true is not allowed",
    });
    return getUpdaterSnapshot();
  }

  if (snapshot.phase !== "downloaded" && snapshot.phase !== "restart_required") {
    setSnapshot({
      phase: "failed",
      message: "请先完成下载，再确认安装。",
      technicalDetail: `invalid phase: ${snapshot.phase}`,
    });
    return getUpdaterSnapshot();
  }

  if (!pendingUpdate && snapshot.latestVersion?.endsWith("-audit")) {
    setSnapshot({
      phase: "restart_required",
      message: "审计模拟：安装完成，需要重启后生效。",
    });
    return getUpdaterSnapshot();
  }

  if (!pendingUpdate) {
    setSnapshot({
      phase: "failed",
      message: "没有可安装的更新包。",
      technicalDetail: "pendingUpdate is null",
    });
    return getUpdaterSnapshot();
  }

  setSnapshot({
    phase: "installing",
    message: "正在安装更新…请勿关闭应用。",
    technicalDetail: null,
  });

  try {
    await pendingUpdate.install();
    await clearPendingUpdate();
    setSnapshot({
      phase: "restart_required",
      message: "更新已安装。请保存工作后重启 StoryLens 以完成更新。",
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setSnapshot({
      phase: "failed",
      message: userFacingError(detail),
      technicalDetail: detail,
    });
  }

  return getUpdaterSnapshot();
}

/** Explicit user action after install — relaunch the app. */
export async function relaunchToApplyUpdate(): Promise<void> {
  if (snapshot.phase !== "restart_required") {
    throw new Error("只能在安装完成后重启应用。");
  }
  if (!isTauriRuntime()) {
    return;
  }
  const { relaunch } = await import("@tauri-apps/plugin-process");
  await relaunch();
}

/** Defer install after download — keep app running. */
export function deferInstall(): UpdaterSnapshot {
  if (snapshot.phase === "downloaded") {
    setSnapshot({
      message: "已下载更新包。可稍后在设置中重启并安装。",
    });
  }
  return getUpdaterSnapshot();
}

export function resetUpdaterFailure(): void {
  if (snapshot.phase === "failed") {
    setSnapshot({
      phase: snapshot.latestVersion ? "available" : "idle",
      message: snapshot.latestVersion ? `发现新版本 ${snapshot.latestVersion}` : "",
      technicalDetail: null,
    });
  }
}

/** Test helper — inject snapshot without Tauri. */
export function __resetUpdaterForTests(): void {
  snapshot = { ...INITIAL_UPDATER_SNAPSHOT };
  pendingUpdate = null;
}

export function __setUpdaterSnapshotForTests(patch: Partial<UpdaterSnapshot>): void {
  setSnapshot(patch);
}
