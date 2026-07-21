import { describe, expect, it } from "vitest";
import {
  formatSceneDisplayLabel,
  formatSceneOrdinalBadge,
} from "./formatSceneDisplayLabel";

describe("formatSceneDisplayLabel", () => {
  it("formats real Scene.ordinal as S01-style badge", () => {
    expect(formatSceneDisplayLabel({ ordinal: 1, scene_key: "B0001-C0001-S0001" })).toBe(
      "S01",
    );
    expect(formatSceneOrdinalBadge({ ordinal: 12 })).toBe("S12");
  });

  it("does not show Sundefined / Snull / SNaN when ordinal is missing", () => {
    expect(formatSceneDisplayLabel({ scene_key: "客厅" })).toBe("客厅");
    expect(formatSceneDisplayLabel({ ordinal: undefined as unknown as number })).toBe("场景");
    expect(formatSceneDisplayLabel({ ordinal: null })).toBe("场景");
    expect(formatSceneDisplayLabel({ ordinal: Number.NaN })).toBe("场景");
    expect(formatSceneDisplayLabel({ ordinal: "1" as unknown as number })).toBe("场景");
    expect(formatSceneOrdinalBadge({ ordinal: undefined })).toBeNull();
    expect(formatSceneDisplayLabel({})).not.toMatch(/undefined|null|NaN/i);
    expect(formatSceneDisplayLabel({ ordinal: null, scene_key: null })).toBe("场景");
  });

  it("ignores dirty scene_key tokens and falls back to 场景", () => {
    expect(formatSceneDisplayLabel({ scene_key: "undefined" })).toBe("场景");
    expect(formatSceneDisplayLabel({ scene_key: "null" })).toBe("场景");
    expect(formatSceneDisplayLabel({ scene_key: "NaN" })).toBe("场景");
  });
});
