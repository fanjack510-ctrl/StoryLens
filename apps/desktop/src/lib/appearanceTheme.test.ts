import { describe, expect, it, beforeEach, afterEach } from "vitest";
import {
  APPEARANCE_THEME_STORAGE_KEY,
  applyAppearanceTheme,
  parseAppearanceTheme,
  readAppearanceTheme,
  writeAppearanceTheme,
} from "./appearanceTheme";

function memoryStorage(seed: Record<string, string> = {}): Storage {
  const map = new Map(Object.entries(seed));
  return {
    get length() {
      return map.size;
    },
    clear() {
      map.clear();
    },
    getItem(key: string) {
      return map.has(key) ? map.get(key)! : null;
    },
    key(index: number) {
      return [...map.keys()][index] ?? null;
    },
    removeItem(key: string) {
      map.delete(key);
    },
    setItem(key: string, value: string) {
      map.set(key, value);
    },
  };
}

describe("appearanceTheme persistence", () => {
  it("parses only light|dark", () => {
    expect(parseAppearanceTheme("light")).toBe("light");
    expect(parseAppearanceTheme("dark")).toBe("dark");
    expect(parseAppearanceTheme("system")).toBeNull();
    expect(parseAppearanceTheme("nope")).toBeNull();
  });

  it("writes canonical key and clears legacy keys", () => {
    const storage = memoryStorage({
      "storylens.theme": "light",
      theme: "light",
    });
    writeAppearanceTheme("dark", storage);
    expect(storage.getItem(APPEARANCE_THEME_STORAGE_KEY)).toBe("dark");
    expect(storage.getItem("storylens.theme")).toBeNull();
    expect(storage.getItem("theme")).toBeNull();
  });

  it("migrates legacy key on read", () => {
    const storage = memoryStorage({ "storylens.theme": "dark" });
    expect(readAppearanceTheme(storage)).toBe("dark");
    expect(storage.getItem(APPEARANCE_THEME_STORAGE_KEY)).toBe("dark");
  });

  it("falls back to light for illegal values", () => {
    const storage = memoryStorage({ [APPEARANCE_THEME_STORAGE_KEY]: "neon" });
    expect(readAppearanceTheme(storage)).toBe("light");
  });

  it("applies data-theme on document element", () => {
    const el = document.createElement("div");
    applyAppearanceTheme("dark", el);
    expect(el.dataset.theme).toBe("dark");
    expect(el.classList.contains("theme-dark")).toBe(true);
    applyAppearanceTheme("light", el);
    expect(el.dataset.theme).toBe("light");
    expect(el.classList.contains("theme-light")).toBe(true);
  });
});

describe("uiStore theme persistence", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset.theme = "";
  });

  afterEach(() => {
    localStorage.clear();
  });

  it("setTheme persists and remount store reads dark", async () => {
    const { useUiStore } = await import("../stores/uiStore");
    useUiStore.setState({ theme: "light" });
    useUiStore.getState().setTheme("dark");
    expect(localStorage.getItem(APPEARANCE_THEME_STORAGE_KEY)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(useUiStore.getState().theme).toBe("dark");
  });
});
