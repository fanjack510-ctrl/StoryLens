/**
 * Build-time injection from vite.config (package.json → synced from VERSION).
 * Used for browser / Vitest only. Tauri production prefers get_app_version.
 * Do not hardcode product versions in UI components.
 */
export const BUILD_APP_VERSION: string =
  typeof __STORYLENS_APP_VERSION__ === "string" ? __STORYLENS_APP_VERSION__ : "";

/** Shown when runtime and build-time version resolution both fail. */
export const UNKNOWN_VERSION_LABEL = "版本未知";

/**
 * @deprecated Prefer resolveAppVersion() / useAppVersion() for display.
 * Kept as the build-injected value for non-UI helpers (e.g. audit mocks).
 */
export const APP_VERSION: string = BUILD_APP_VERSION;

function isTauriRuntime(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function formatAppVersionLabel(version: string | null | undefined): string {
  const trimmed = typeof version === "string" ? version.trim() : "";
  return trimmed || UNKNOWN_VERSION_LABEL;
}

/**
 * Resolve the real application version.
 * 1) Tauri runtime → invoke get_app_version
 * 2) Browser / tests → build-injected __STORYLENS_APP_VERSION__
 * 3) Otherwise empty (callers show UNKNOWN_VERSION_LABEL)
 *
 * Intentionally no production hardcoded fallback like "1.0.1".
 */
export async function resolveAppVersion(): Promise<string> {
  if (isTauriRuntime()) {
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const runtime = await invoke<string>("get_app_version");
      if (typeof runtime === "string" && runtime.trim()) {
        return runtime.trim();
      }
    } catch {
      // Fall through to build injection / unknown.
    }
  }

  if (BUILD_APP_VERSION.trim()) {
    return BUILD_APP_VERSION.trim();
  }
  return "";
}
