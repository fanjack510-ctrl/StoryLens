/**
 * STEP 2.2 / 2.3-C — Pro Native Whole-Book Overview UI gate + engine labels.
 * Backend enforces PRO_NATIVE_OVERVIEW_ENABLED independently; this is UI-only.
 * Default: off. Do not treat Fixture results as production AI overview.
 */
export const PRO_NATIVE_OVERVIEW_ENABLED_ENV = "PRO_NATIVE_OVERVIEW_ENABLED";

export const FIXTURE_ENGINE_ID = "fixture-native-overview-v1";
export const FIXTURE_ENGINE_VERSION = "walking-skeleton-1";
export const FIXTURE_PROMPT_VERSION = "fixture-no-prompt";

/** Formal Private engine id (STEP 2.3-B). Never silently relabel as Fixture. */
export const PRIVATE_NATIVE_OVERVIEW_ENGINE_ID = "private-native-overview-v1";

export const FIXTURE_ENGINE_LABEL = "Fixture Development Mode";
export const FORMAL_ENGINE_LABEL = "Formal Overview Engine";

export const WALKING_SKELETON_USER_NOTICE =
  "当前为行走骨架验证，不调用真实 AI Provider。";

export const FIXTURE_DEVELOPMENT_WARNING =
  "Fixture execution does not call a provider.";

export type EnginePresentationKind = "fixture" | "formal" | "unknown";

export type EnginePresentation = {
  kind: EnginePresentationKind;
  label: string;
  isFixture: boolean;
  engineId: string | null;
};

/** Resolve Fixture vs formal engine labeling from engine_id (or model_id fallback). */
export function resolveEnginePresentation(
  engineId?: string | null,
  modelId?: string | null,
): EnginePresentation {
  const id = (engineId || modelId || "").trim();
  if (!id) {
    return {
      kind: "unknown",
      label: "Engine 未指定",
      isFixture: false,
      engineId: null,
    };
  }
  if (id === FIXTURE_ENGINE_ID || id.startsWith("fixture-")) {
    return {
      kind: "fixture",
      label: FIXTURE_ENGINE_LABEL,
      isFixture: true,
      engineId: id,
    };
  }
  if (id === PRIVATE_NATIVE_OVERVIEW_ENGINE_ID || id.startsWith("private-")) {
    return {
      kind: "formal",
      label: FORMAL_ENGINE_LABEL,
      isFixture: false,
      engineId: id,
    };
  }
  return {
    kind: "formal",
    label: FORMAL_ENGINE_LABEL,
    isFixture: false,
    engineId: id,
  };
}

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
