/**
 * Persistent appearance theme — single source of truth for Header, Settings, bootstrap.
 * Values: light | dark only (no system follow).
 */

export type AppearanceTheme = "light" | "dark";

export const APPEARANCE_THEME_STORAGE_KEY = "storylens.appearance.theme";

/** Legacy keys read once for migration; new writes use APPEARANCE_THEME_STORAGE_KEY only. */
export const APPEARANCE_THEME_LEGACY_KEYS = [
  "storylens.theme",
  "storylens.ui.theme",
  "theme",
] as const;

export const DEFAULT_APPEARANCE_THEME: AppearanceTheme = "light";

export function parseAppearanceTheme(raw: string | null | undefined): AppearanceTheme | null {
  if (raw === "light" || raw === "dark") return raw;
  return null;
}

export function appearanceThemeLabel(theme: AppearanceTheme): string {
  return theme === "dark" ? "深色" : "浅色";
}

export function readAppearanceTheme(
  storage: Pick<Storage, "getItem" | "setItem" | "removeItem"> | null = typeof localStorage !==
  "undefined"
    ? localStorage
    : null,
): AppearanceTheme {
  if (!storage) return DEFAULT_APPEARANCE_THEME;
  try {
    const primary = parseAppearanceTheme(storage.getItem(APPEARANCE_THEME_STORAGE_KEY));
    if (primary) return primary;
    for (const key of APPEARANCE_THEME_LEGACY_KEYS) {
      const legacy = parseAppearanceTheme(storage.getItem(key));
      if (legacy) {
        writeAppearanceTheme(legacy, storage);
        return legacy;
      }
    }
  } catch {
    /* ignore quota / private mode */
  }
  return DEFAULT_APPEARANCE_THEME;
}

export function writeAppearanceTheme(
  theme: AppearanceTheme,
  storage: Pick<Storage, "setItem" | "removeItem"> | null = typeof localStorage !== "undefined"
    ? localStorage
    : null,
): void {
  if (!storage) return;
  try {
    storage.setItem(APPEARANCE_THEME_STORAGE_KEY, theme);
    for (const key of APPEARANCE_THEME_LEGACY_KEYS) {
      try {
        storage.removeItem(key);
      } catch {
        /* ignore */
      }
    }
  } catch {
    /* ignore */
  }
}

/** Apply theme to documentElement (pre-React + runtime). .app also sets data-theme from store. */
export function applyAppearanceTheme(theme: AppearanceTheme, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = theme;
  root.classList.toggle("theme-dark", theme === "dark");
  root.classList.toggle("theme-light", theme === "light");
}
