/**
 * STEP 2.2 — Pro Native Whole-Book Overview walking skeleton gate.
 * Backend enforces PRO_NATIVE_OVERVIEW_ENABLED independently; this is UI-only.
 * Default: off. Do not treat as production AI overview.
 */
export const PRO_NATIVE_OVERVIEW_ENABLED_ENV = "PRO_NATIVE_OVERVIEW_ENABLED";

export const FIXTURE_ENGINE_ID = "fixture-native-overview-v1";
export const FIXTURE_ENGINE_VERSION = "walking-skeleton-1";
export const FIXTURE_PROMPT_VERSION = "fixture-no-prompt";

export const WALKING_SKELETON_USER_NOTICE =
  "当前为行走骨架验证，不调用真实 AI Provider。";

/** Desktop presentation gate — reads Vite/Electron env when present. */
export function isProNativeOverviewUiEnabled(): boolean {
  const raw =
    (typeof import.meta !== "undefined" &&
      (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
        "VITE_PRO_NATIVE_OVERVIEW_ENABLED"
      ]) ||
    (typeof process !== "undefined" && process.env?.[PRO_NATIVE_OVERVIEW_ENABLED_ENV]) ||
    "false";
  const value = String(raw).trim().toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}
