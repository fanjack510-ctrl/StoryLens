/**
 * Pure display label for workspace scene directory rows.
 * Uses Scene.ordinal from the real API contract (GET /chapters/{id}/scenes → SceneResponse).
 * Never invents ordinals from list index; never stringifies null/undefined/NaN as "S…".
 */

export type SceneDisplaySource = {
  ordinal?: number | null;
  scene_key?: string | null;
};

function isValidOrdinal(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** Compact badge text like S01 / S12 when ordinal is present. */
export function formatSceneOrdinalBadge(scene: SceneDisplaySource): string | null {
  if (!isValidOrdinal(scene.ordinal)) return null;
  return `S${String(Math.trunc(scene.ordinal)).padStart(2, "0")}`;
}

/**
 * Primary row label for the scene catalog.
 * Prefers real ordinal (S01); otherwise scene_key; otherwise a neutral "场景".
 */
export function formatSceneDisplayLabel(scene: SceneDisplaySource): string {
  const badge = formatSceneOrdinalBadge(scene);
  if (badge) return badge;
  const key = typeof scene.scene_key === "string" ? scene.scene_key.trim() : "";
  if (key && !/^(undefined|null|NaN)$/i.test(key)) return key;
  return "场景";
}
