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
export const UNKNOWN_ENGINE_LABEL = "引擎信息不可用";

export const WALKING_SKELETON_USER_NOTICE =
  "当前为行走骨架验证，不调用真实 AI Provider。";

export const FIXTURE_DEVELOPMENT_WARNING =
  "Fixture execution does not call a provider.";

/** Product presentation kinds for result / preflight badges. */
export type EnginePresentationKind = "formal" | "walking_skeleton" | "unknown";

export type EnginePresentation = {
  kind: EnginePresentationKind;
  label: string;
  /** True only for real fixture / walking-skeleton engines. */
  isFixture: boolean;
  /** Alias of isFixture — when true, walking-skeleton notice may show. */
  showWalkingSkeletonNotice: boolean;
  engineId: string | null;
};

export type ResolveEnginePresentationInput = {
  engineId?: string | null;
  modelId?: string | null;
  engineVersion?: string | null;
  contractVersion?: string | null;
};

function isWalkingSkeletonId(id: string): boolean {
  if (id === FIXTURE_ENGINE_ID || id.startsWith("fixture-")) return true;
  if (id.includes("walking-skeleton") || id.includes("walking_skeleton")) return true;
  return false;
}

/**
 * Resolve formal vs walking-skeleton vs unknown from engine identity.
 * Missing engine_id must NOT claim "no Provider was called".
 */
export function resolveEnginePresentation(
  engineIdOrInput?: string | null | ResolveEnginePresentationInput,
  modelId?: string | null,
): EnginePresentation {
  const input: ResolveEnginePresentationInput =
    engineIdOrInput != null && typeof engineIdOrInput === "object"
      ? engineIdOrInput
      : { engineId: engineIdOrInput, modelId };

  const id = (input.engineId || input.modelId || "").trim();
  if (!id) {
    return {
      kind: "unknown",
      label: UNKNOWN_ENGINE_LABEL,
      isFixture: false,
      showWalkingSkeletonNotice: false,
      engineId: null,
    };
  }
  if (isWalkingSkeletonId(id)) {
    return {
      kind: "walking_skeleton",
      label: FIXTURE_ENGINE_LABEL,
      isFixture: true,
      showWalkingSkeletonNotice: true,
      engineId: id,
    };
  }
  if (id === PRIVATE_NATIVE_OVERVIEW_ENGINE_ID || id.startsWith("private-")) {
    return {
      kind: "formal",
      label: FORMAL_ENGINE_LABEL,
      isFixture: false,
      showWalkingSkeletonNotice: false,
      engineId: id,
    };
  }
  // Unknown non-empty id: treat as formal-capable production binding, not skeleton.
  return {
    kind: "formal",
    label: FORMAL_ENGINE_LABEL,
    isFixture: false,
    showWalkingSkeletonNotice: false,
    engineId: id,
  };
}

function envFlagTruthy(raw: unknown): boolean {
  const value = String(raw ?? "")
    .trim()
    .toLowerCase();
  return value === "1" || value === "true" || value === "yes" || value === "on";
}

/**
 * Desktop presentation gate.
 * Priority: Vite import.meta env → build-time define (RC may bake true) → process env.
 * Repository / non-RC production default remains false.
 */
export function isProNativeOverviewUiEnabled(): boolean {
  const fromVite =
    typeof import.meta !== "undefined"
      ? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.[
          "VITE_PRO_NATIVE_OVERVIEW_ENABLED"
        ]
      : undefined;
  if (fromVite !== undefined && String(fromVite).trim() !== "") {
    return envFlagTruthy(fromVite);
  }
  if (
    typeof __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__ !== "undefined" &&
    __STORYLENS_PRO_NATIVE_OVERVIEW_ENABLED__ === true
  ) {
    return true;
  }
  if (typeof process !== "undefined" && process.env?.[PRO_NATIVE_OVERVIEW_ENABLED_ENV]) {
    return envFlagTruthy(process.env[PRO_NATIVE_OVERVIEW_ENABLED_ENV]);
  }
  return false;
}
