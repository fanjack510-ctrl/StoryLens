import { create } from "zustand";
import {
  applyAppearanceTheme,
  readAppearanceTheme,
  writeAppearanceTheme,
  type AppearanceTheme,
} from "../lib/appearanceTheme";
import {
  applyInterfaceZoom,
  applyInterfaceZoomCss,
  parseInterfaceZoom,
  readInterfaceZoom,
  type InterfaceZoomPercent,
} from "../lib/interfaceZoom";
import {
  readReadingSettings,
  writeReadingSettings,
  type ContentWidth,
  type ReadingSettings,
} from "../lib/readingSettings";

type State = {
  theme: AppearanceTheme;
  demo: boolean;
  fontSize: number;
  lineHeight: number;
  contentWidth: ContentWidth;
  showParagraphIds: boolean;
  interfaceZoom: InterfaceZoomPercent;
  setTheme: (v: AppearanceTheme) => void;
  setDemo: (v: boolean) => void;
  setReading: (fontSize: number, lineHeight: number) => void;
  setContentWidth: (v: ContentWidth) => void;
  setShowParagraphIds: (v: boolean) => void;
  setInterfaceZoom: (v: InterfaceZoomPercent | number) => Promise<void>;
};

function hydrateTheme(): AppearanceTheme {
  const theme = readAppearanceTheme();
  if (typeof document !== "undefined") {
    applyAppearanceTheme(theme);
  }
  return theme;
}

function hydrateInterfaceZoom(): InterfaceZoomPercent {
  const zoom = readInterfaceZoom();
  if (typeof document !== "undefined") {
    // Sync CSS immediately; Tauri setZoom is applied async from App / setInterfaceZoom.
    applyInterfaceZoomCss(zoom);
  }
  return zoom;
}

/** Reading settings are read once at startup and written on every change, the same way theme
 *  and zoom already work. Before this they lived only in memory, so enlarging the text lasted
 *  until the next restart — which reads as the control not working. */
const reading = readReadingSettings();

/** Merge one changed field into the other three and write all four, so the stored object is
 *  always a whole settings record rather than whichever field was touched last. */
function persistReading(next: Partial<ReadingSettings>) {
  return (state: State): Partial<State> => {
    const merged: ReadingSettings = {
      fontSize: next.fontSize ?? state.fontSize,
      lineHeight: next.lineHeight ?? state.lineHeight,
      contentWidth: next.contentWidth ?? state.contentWidth,
      showParagraphIds: next.showParagraphIds ?? state.showParagraphIds,
    };
    writeReadingSettings(merged);
    return merged;
  };
}

export const useUiStore = create<State>((set) => ({
  theme: hydrateTheme(),
  demo: true,
  fontSize: reading.fontSize,
  lineHeight: reading.lineHeight,
  contentWidth: reading.contentWidth,
  showParagraphIds: reading.showParagraphIds,
  interfaceZoom: hydrateInterfaceZoom(),
  setTheme: (theme) => {
    writeAppearanceTheme(theme);
    if (typeof document !== "undefined") {
      applyAppearanceTheme(theme);
    }
    set({ theme });
  },
  setDemo: (demo) => set({ demo }),
  setReading: (fontSize, lineHeight) => set(persistReading({ fontSize, lineHeight })),
  setContentWidth: (contentWidth) => set(persistReading({ contentWidth })),
  setShowParagraphIds: (showParagraphIds) => set(persistReading({ showParagraphIds })),
  setInterfaceZoom: async (raw) => {
    const percent = parseInterfaceZoom(raw);
    set({ interfaceZoom: percent });
    await applyInterfaceZoom(percent);
  },
}));
