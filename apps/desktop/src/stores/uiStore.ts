import { create } from "zustand";
import {
  applyAppearanceTheme,
  readAppearanceTheme,
  writeAppearanceTheme,
  type AppearanceTheme,
} from "../lib/appearanceTheme";

type ContentWidth = "narrow" | "normal" | "wide";

type State = {
  theme: AppearanceTheme;
  demo: boolean;
  fontSize: number;
  lineHeight: number;
  contentWidth: ContentWidth;
  showParagraphIds: boolean;
  setTheme: (v: AppearanceTheme) => void;
  setDemo: (v: boolean) => void;
  setReading: (fontSize: number, lineHeight: number) => void;
  setContentWidth: (v: ContentWidth) => void;
  setShowParagraphIds: (v: boolean) => void;
};

function hydrateTheme(): AppearanceTheme {
  const theme = readAppearanceTheme();
  if (typeof document !== "undefined") {
    applyAppearanceTheme(theme);
  }
  return theme;
}

export const useUiStore = create<State>((set) => ({
  theme: hydrateTheme(),
  demo: true,
  fontSize: 17,
  lineHeight: 1.9,
  contentWidth: "wide",
  showParagraphIds: false,
  setTheme: (theme) => {
    writeAppearanceTheme(theme);
    if (typeof document !== "undefined") {
      applyAppearanceTheme(theme);
    }
    set({ theme });
  },
  setDemo: (demo) => set({ demo }),
  setReading: (fontSize, lineHeight) => set({ fontSize, lineHeight }),
  setContentWidth: (contentWidth) => set({ contentWidth }),
  setShowParagraphIds: (showParagraphIds) => set({ showParagraphIds }),
}));
