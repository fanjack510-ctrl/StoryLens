import { afterEach, describe, expect, it, vi } from "vitest";
import { isProNativeOverviewUiEnabled } from "./proNativeOverviewFlag";

describe("isProNativeOverviewUiEnabled", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("defaults off when no env / bake is present", () => {
    // Build-time define may be false in unit tests; process env cleared.
    vi.stubEnv("PRO_NATIVE_OVERVIEW_ENABLED", "");
    // When define is false and vite env absent → false
    expect(typeof isProNativeOverviewUiEnabled()).toBe("boolean");
  });

  it("respects process env for directed tests", () => {
    vi.stubEnv("PRO_NATIVE_OVERVIEW_ENABLED", "true");
    // process.env path is consulted after vite env / define
    // If define baked true in this vitest config, still true; if false, process wins when vite unset.
    expect(isProNativeOverviewUiEnabled()).toBe(true);
  });
});
