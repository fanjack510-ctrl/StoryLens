import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DEFAULT_INTERFACE_ZOOM,
  INTERFACE_ZOOM_LEVELS,
  INTERFACE_ZOOM_STORAGE_KEY,
  applyInterfaceZoom,
  applyInterfaceZoomCss,
  parseInterfaceZoom,
  readInterfaceZoom,
  shouldIgnoreInterfaceZoomShortcut,
  stepInterfaceZoom,
  writeInterfaceZoom,
} from "./interfaceZoom";

function memoryStorage(seed: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(seed));
  return {
    get length() {
      return map.size;
    },
    clear: () => map.clear(),
    getItem: (k) => (map.has(k) ? map.get(k)! : null),
    setItem: (k, v) => {
      map.set(k, String(v));
    },
    removeItem: (k) => {
      map.delete(k);
    },
    key: (i) => Array.from(map.keys())[i] ?? null,
  };
}

describe("interfaceZoom", () => {
  beforeEach(() => {
    document.documentElement.style.zoom = "";
    document.documentElement.style.removeProperty("--storylens-interface-zoom");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("defaults to 100 and accepts discrete levels", () => {
    expect(parseInterfaceZoom(undefined)).toBe(100);
    expect(parseInterfaceZoom("bogus")).toBe(100);
    expect(parseInterfaceZoom(99)).toBe(100);
    for (const level of INTERFACE_ZOOM_LEVELS) {
      expect(parseInterfaceZoom(level)).toBe(level);
      expect(parseInterfaceZoom(String(level))).toBe(level);
    }
  });

  it("persists and restores zoom percent", () => {
    const storage = memoryStorage();
    writeInterfaceZoom(125, storage);
    expect(storage.getItem(INTERFACE_ZOOM_STORAGE_KEY)).toBe("125");
    expect(readInterfaceZoom(storage)).toBe(125);
  });

  it("falls back to 100 for illegal stored values", () => {
    const storage = memoryStorage({ [INTERFACE_ZOOM_STORAGE_KEY]: "133" });
    expect(readInterfaceZoom(storage)).toBe(DEFAULT_INTERFACE_ZOOM);
  });

  it("steps within bounds", () => {
    expect(stepInterfaceZoom(80, -1)).toBe(80);
    expect(stepInterfaceZoom(80, 1)).toBe(90);
    expect(stepInterfaceZoom(150, 1)).toBe(150);
    expect(stepInterfaceZoom(150, -1)).toBe(125);
    expect(stepInterfaceZoom(100, 1)).toBe(110);
  });

  it("applies CSS zoom as fallback path", async () => {
    const storage = memoryStorage();
    const mode = await applyInterfaceZoom(110, { storage, root: document.documentElement });
    expect(mode).toBe("css_zoom");
    expect(document.documentElement.style.zoom).toBe("1.1");
    expect(document.documentElement.style.getPropertyValue("--storylens-interface-zoom")).toBe(
      "1.1",
    );
    expect(readInterfaceZoom(storage)).toBe(110);
  });

  it("applyInterfaceZoomCss sets root zoom immediately", () => {
    applyInterfaceZoomCss(150, document.documentElement);
    expect(document.documentElement.style.zoom).toBe("1.5");
  });

  it("ignores shortcuts in editable fields", () => {
    const input = document.createElement("input");
    expect(shouldIgnoreInterfaceZoomShortcut(input)).toBe(true);
    const div = document.createElement("div");
    expect(shouldIgnoreInterfaceZoomShortcut(div)).toBe(false);
  });
});
