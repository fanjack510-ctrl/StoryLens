/**
 * Development / diagnostics runtime fingerprint.
 * Production builds must not surface this in the main chrome.
 */

import { getApiBase, isApiBaseReady } from "./apiClient";
import { isTauriRuntime } from "./desktopRuntime";

declare const __STORYLENS_PUBLIC_GIT_HEAD__: string | undefined;
declare const __STORYLENS_APP_VERSION__: string | undefined;

export type RuntimeFingerprint = {
  mode: "development" | "production";
  publicHead: string;
  appVersion: string;
  apiBase: string;
  apiPort: string;
  apiReady: boolean;
  tauri: boolean;
};

function resolvePublicHead(): string {
  const fromEnv =
    typeof import.meta.env.VITE_PUBLIC_GIT_HEAD === "string"
      ? import.meta.env.VITE_PUBLIC_GIT_HEAD.trim()
      : "";
  if (fromEnv) return fromEnv;
  const injected =
    typeof __STORYLENS_PUBLIC_GIT_HEAD__ === "string" ? __STORYLENS_PUBLIC_GIT_HEAD__.trim() : "";
  return injected || "unknown";
}

export function getRuntimeFingerprint(): RuntimeFingerprint {
  const base = getApiBase();
  let apiPort = "";
  try {
    if (base) apiPort = new URL(base).port || (base.startsWith("https") ? "443" : "80");
  } catch {
    apiPort = "";
  }
  const head = resolvePublicHead();
  return {
    mode: import.meta.env.DEV ? "development" : "production",
    publicHead: head.slice(0, 12),
    appVersion:
      typeof __STORYLENS_APP_VERSION__ === "string" ? __STORYLENS_APP_VERSION__ : "unknown",
    apiBase: base || "(same-origin)",
    apiPort: apiPort || "—",
    apiReady: isApiBaseReady(),
    tauri: isTauriRuntime(),
  };
}

export function formatRuntimeFingerprint(fp: RuntimeFingerprint = getRuntimeFingerprint()): string {
  return `DEV Public ${fp.publicHead} · API ${fp.apiPort || fp.apiBase}`;
}
