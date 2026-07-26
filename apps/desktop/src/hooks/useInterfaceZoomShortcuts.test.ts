import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { useInterfaceZoomShortcuts } from "./useInterfaceZoomShortcuts";
import { INTERFACE_ZOOM_STORAGE_KEY } from "../lib/interfaceZoom";
import { useUiStore } from "../stores/uiStore";

describe("useInterfaceZoomShortcuts", () => {
  beforeEach(() => {
    localStorage.clear();
    useUiStore.setState({ interfaceZoom: 100 });
    document.documentElement.style.zoom = "";
  });

  afterEach(() => {
    cleanup();
  });

  it("Ctrl+0 restores product default 80%", async () => {
    renderHook(() => useInterfaceZoomShortcuts());
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "0", code: "Digit0", ctrlKey: true, bubbles: true }),
    );
    expect(useUiStore.getState().interfaceZoom).toBe(80);
    expect(localStorage.getItem(INTERFACE_ZOOM_STORAGE_KEY)).toBe("80");
  });
});
