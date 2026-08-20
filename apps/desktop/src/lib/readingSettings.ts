/**
 * Persistent reading settings — font size, line height, content width, paragraph ids.
 *
 * These four lived only in the zustand store, so every one of them reset on restart. A
 * reader who enlarges the text because the default is too small has to do it again every
 * time the app opens, which reads as the setting not working rather than not persisting.
 *
 * Theme and interface zoom already persist through their own helpers in this folder; this
 * follows the same shape rather than wrapping the whole store in persist middleware, which
 * would put a second writer on keys those two already own.
 */

export type ContentWidth = "narrow" | "normal" | "wide";

export type ReadingSettings = {
  fontSize: number;
  lineHeight: number;
  contentWidth: ContentWidth;
  showParagraphIds: boolean;
};

export const READING_SETTINGS_STORAGE_KEY = "storylens.reading.settings";

export const DEFAULT_READING_SETTINGS: ReadingSettings = {
  fontSize: 17,
  lineHeight: 1.9,
  contentWidth: "wide",
  showParagraphIds: false,
};

/** The bounds the popover itself enforces. Stored values are clamped to them on read, so a
 *  hand-edited or stale entry cannot produce a page no control can bring back. */
const FONT_SIZE_MIN = 14;
const FONT_SIZE_MAX = 28;
const LINE_HEIGHT_MIN = 1.2;
const LINE_HEIGHT_MAX = 2.6;

const clamp = (value: number, lo: number, hi: number): number =>
  Math.min(hi, Math.max(lo, value));

function parseContentWidth(raw: unknown): ContentWidth | null {
  return raw === "narrow" || raw === "normal" || raw === "wide" ? raw : null;
}

export function parseReadingSettings(raw: string | null | undefined): ReadingSettings | null {
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const value = parsed as Partial<Record<keyof ReadingSettings, unknown>>;
    const fontSize = Number(value.fontSize);
    const lineHeight = Number(value.lineHeight);
    return {
      fontSize: Number.isFinite(fontSize)
        ? clamp(Math.round(fontSize), FONT_SIZE_MIN, FONT_SIZE_MAX)
        : DEFAULT_READING_SETTINGS.fontSize,
      lineHeight: Number.isFinite(lineHeight)
        ? clamp(lineHeight, LINE_HEIGHT_MIN, LINE_HEIGHT_MAX)
        : DEFAULT_READING_SETTINGS.lineHeight,
      contentWidth: parseContentWidth(value.contentWidth) ?? DEFAULT_READING_SETTINGS.contentWidth,
      showParagraphIds:
        typeof value.showParagraphIds === "boolean"
          ? value.showParagraphIds
          : DEFAULT_READING_SETTINGS.showParagraphIds,
    };
  } catch {
    return null;
  }
}

type MinimalStorage = Pick<Storage, "getItem" | "setItem">;

const defaultStorage = (): MinimalStorage | null =>
  typeof localStorage !== "undefined" ? localStorage : null;

export function readReadingSettings(
  storage: MinimalStorage | null = defaultStorage(),
): ReadingSettings {
  if (!storage) return DEFAULT_READING_SETTINGS;
  try {
    return (
      parseReadingSettings(storage.getItem(READING_SETTINGS_STORAGE_KEY)) ??
      DEFAULT_READING_SETTINGS
    );
  } catch {
    return DEFAULT_READING_SETTINGS;
  }
}

/** Writing must never be able to break reading: a full storage quota is not a reason for the
 *  page to stop responding to the control the reader just moved. */
export function writeReadingSettings(
  settings: ReadingSettings,
  storage: MinimalStorage | null = defaultStorage(),
): void {
  if (!storage) return;
  try {
    storage.setItem(READING_SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  } catch {
    /* ignore */
  }
}
