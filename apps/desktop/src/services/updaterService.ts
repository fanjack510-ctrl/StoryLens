import { APP_VERSION } from "../lib/appVersion";

export type UpdateCheckResult =
  | { kind: "disabled" }
  | { kind: "latest"; currentVersion: string }
  | {
      kind: "available";
      currentVersion: string;
      latestVersion: string;
      body: string;
      downloadAndInstall: () => Promise<void>;
    }
  | { kind: "error"; message: string };

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function checkForAppUpdate(manual = false): Promise<UpdateCheckResult> {
  // UI audit (browser): surface a real update dialog without Tauri / cloud calls.
  if (
    typeof sessionStorage !== "undefined" &&
    sessionStorage.getItem("storylens.uiAudit") === "1" &&
    manual
  ) {
    return {
      kind: "available",
      currentVersion: APP_VERSION,
      latestVersion: `${APP_VERSION}-audit`,
      body: "审计模拟更新说明：稳定性修复与界面安全基线。",
      downloadAndInstall: async () => undefined,
    };
  }

  if (!isTauriRuntime()) {
    return { kind: "disabled" };
  }

  try {
    const { invoke } = await import("@tauri-apps/api/core");
    const enabled = await invoke<boolean>("updater_enabled");
    if (!enabled) {
      return { kind: "disabled" };
    }

    const currentVersion = await invoke<string>("get_app_version");
    const { check } = await import("@tauri-apps/plugin-updater");
    const { relaunch } = await import("@tauri-apps/plugin-process");
    const update = await check();

    if (!update) {
      return { kind: "latest", currentVersion };
    }

    return {
      kind: "available",
      currentVersion,
      latestVersion: update.version,
      body: update.body || "修复问题并改进稳定性。",
      downloadAndInstall: async () => {
        await update.downloadAndInstall();
        await relaunch();
      },
    };
  } catch (error) {
    // Never block local analysis; surface a soft message only for manual checks.
    const detail = error instanceof Error ? error.message : String(error);
    if (!manual) {
      console.warn("update check failed (ignored):", detail);
      return { kind: "disabled" };
    }
    return {
      kind: "error",
      message: "检查更新失败。这不影响本地分析，请稍后重试或检查网络。",
    };
  }
}
