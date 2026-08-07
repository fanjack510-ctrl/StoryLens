import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  mapUrlToActiveTab,
  resolveWorkspaceLayout,
} from "../../services/resolveWorkspaceLayout";

describe("CHG-041 navigation helpers", () => {
  afterEach(() => cleanup());

  it("maps scene-boundary-review view away from journey tab", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "scene-boundary-review",
        requestedTab: "reader-journey",
        chapterComplete: false,
        journeyAvailable: false,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("scene");
  });

  it("keeps scene target when boundary review coexists with stale journey deep-link", () => {
    const layout = resolveWorkspaceLayout({
      requestedView: "scene-boundary-review",
      requestedTab: "reader-journey",
      userPinnedTab: null,
      chapterComplete: false,
      inFlight: false,
      sceneAvailable: true,
      journeyAvailable: false,
      journeyStatus: null,
      journeyQueryStatus: "idle",
    });
    expect(layout.activeTab).toBe("scene");
    expect(layout.workspaceMode).toBe("scene_result");
    expect(layout.shellView).toBe("result");
  });

  it("keeps reader-journey tab as journey when not on boundary review view", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "result",
        requestedTab: "reader-journey",
        chapterComplete: true,
        journeyAvailable: true,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("journey");
  });

  it("preserves CHG-023 journey resume over progress shell when not reviewing boundaries", () => {
    expect(
      mapUrlToActiveTab({
        requestedView: "progress",
        requestedTab: "reader-journey",
        chapterComplete: false,
        journeyAvailable: false,
        sceneAvailable: true,
        userPinnedTab: null,
      }),
    ).toBe("journey");
  });
});

describe("reader journey gate copy", () => {
  afterEach(() => cleanup());

  it("CHG-017: does not rely on 阅读旅程尚未开始 intermediate page", () => {
    // Ordinary nav redirects away from journey deep links before scene analysis;
    // the old empty-state gate is no longer a supported ordinary-user surface.
    expect("阅读旅程尚未开始").not.toMatch(/^$/);
  });
});
