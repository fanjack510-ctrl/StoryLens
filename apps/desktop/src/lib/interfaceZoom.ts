/**
 * Global interface zoom (browser-like). Discrete percents only.
 * Prefer Tauri Webview.setZoom; CSS zoom is the non-Tauri / fallback path.
 */

import { isTauriRuntime } from "../services/desktopRuntime";

export const INTERFACE_ZOOM_STORAGE_KEY = "storylens.appearance.interfaceZoom";

export const INTERFACE_ZOOM_LEVELS = [80, 90, 100, 110, 125, 150] as const;

export type InterfaceZoomPercent = (typeof INTERFACE_ZOOM_LEVELS)[number];

/** Product default for first launch / missing / invalid stored values. */
export const DEFAULT_INTERFACE_ZOOM: InterfaceZoomPercent = 80;

export type InterfaceZoomApplyMode = "tauri_webview" | "css_zoom";

let lastApplyMode: InterfaceZoomApplyMode = "css_zoom";

export function getLastInterfaceZoomApplyMode(): InterfaceZoomApplyMode {
  return lastApplyMode;
}

export function parseInterfaceZoom(raw: unknown): InterfaceZoomPercent {
  const n = typeof raw === "number" ? raw : Number(String(raw ?? "").trim());
  if (!Number.isFinite(n)) return DEFAULT_INTERFACE_ZOOM;
  const rounded = Math.round(n);
  return (INTERFACE_ZOOM_LEVELS as readonly number[]).includes(rounded)
    ? (rounded as InterfaceZoomPercent)
    : DEFAULT_INTERFACE_ZOOM;
}

export function interfaceZoomFactor(percent: InterfaceZoomPercent): number {
  return percent / 100;
}

export function readInterfaceZoom(
  storage: Pick<Storage, "getItem"> | null = typeof localStorage !== "undefined"
    ? localStorage
    : null,
): InterfaceZoomPercent {
  if (!storage) return DEFAULT_INTERFACE_ZOOM;
  try {
    return parseInterfaceZoom(storage.getItem(INTERFACE_ZOOM_STORAGE_KEY));
  } catch {
    return DEFAULT_INTERFACE_ZOOM;
  }
}

export function writeInterfaceZoom(
  percent: InterfaceZoomPercent,
  storage: Pick<Storage, "setItem"> | null = typeof localStorage !== "undefined"
    ? localStorage
    : null,
): void {
  if (!storage) return;
  try {
    storage.setItem(INTERFACE_ZOOM_STORAGE_KEY, String(percent));
  } catch {
    /* ignore quota / private mode */
  }
}

function applyCssZoom(percent: InterfaceZoomPercent, root: HTMLElement = document.documentElement): void {
  const factor = String(interfaceZoomFactor(percent));
  root.style.setProperty("--storylens-interface-zoom", factor);
  root.style.zoom = factor;
  lastApplyMode = "css_zoom";
}

function clearCssZoom(root: HTMLElement = document.documentElement): void {
  root.style.removeProperty("zoom");
  root.style.removeProperty("--storylens-interface-zoom");
}

/** Sync CSS apply for early bootstrap (index.html / pre-React). */
export function applyInterfaceZoomCss(
  percent: InterfaceZoomPercent,
  root: HTMLElement = document.documentElement,
): void {
  applyCssZoom(percent, root);
}

/**
 * Apply zoom: Tauri Webview.setZoom when available; otherwise CSS zoom.
 * Always persists the discrete percent.
 */
export async function applyInterfaceZoom(
  percent: InterfaceZoomPercent,
  options?: {
    storage?: Pick<Storage, "getItem" | "setItem"> | null;
    root?: HTMLElement;
  },
): Promise<InterfaceZoomApplyMode> {
  const value = parseInterfaceZoom(percent);
  const storage =
    options?.storage === undefined
      ? typeof localStorage !== "undefined"
        ? localStorage
        : null
      : options.storage;
  writeInterfaceZoom(value, storage);

  const root =
    options?.root ?? (typeof document !== "undefined" ? document.documentElement : undefined);

  if (isTauriRuntime()) {
    try {
      const { getCurrentWebview } = await import("@tauri-apps/api/webview");
      await getCurrentWebview().setZoom(interfaceZoomFactor(value));
      if (root) clearCssZoom(root);
      lastApplyMode = "tauri_webview";
      return "tauri_webview";
    } catch {
      /* fall through to CSS */
    }
  }

  if (root) applyCssZoom(value, root);
  else lastApplyMode = "css_zoom";
  return "css_zoom";
}

export function stepInterfaceZoom(
  current: InterfaceZoomPercent,
  delta: 1 | -1,
): InterfaceZoomPercent {
  const idx = INTERFACE_ZOOM_LEVELS.indexOf(parseInterfaceZoom(current));
  const safeIdx = idx < 0 ? INTERFACE_ZOOM_LEVELS.indexOf(DEFAULT_INTERFACE_ZOOM) : idx;
  const next = Math.min(
    INTERFACE_ZOOM_LEVELS.length - 1,
    Math.max(0, safeIdx + delta),
  );
  return INTERFACE_ZOOM_LEVELS[next];
}

/** True when Ctrl/Meta zoom shortcut should be ignored (editable field). */
export function shouldIgnoreInterfaceZoomShortcut(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  if (target.isContentEditable) return true;
  return Boolean(target.closest("[contenteditable='true']"));
}
