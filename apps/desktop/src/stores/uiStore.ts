import { create } from "zustand";

type Theme = "light" | "dark";
type ContentWidth = "narrow" | "normal" | "wide";

type State = {
  theme: Theme;
  demo: boolean;
  fontSize: number;
  lineHeight: number;
  contentWidth: ContentWidth;
  showParagraphIds: boolean;
  setTheme: (v: Theme) => void;
  setDemo: (v: boolean) => void;
  setReading: (fontSize: number, lineHeight: number) => void;
  setContentWidth: (v: ContentWidth) => void;
  setShowParagraphIds: (v: boolean) => void;
};

export const useUiStore = create<State>((set) => ({
  theme: "light",
  demo: true,
  fontSize: 17,
  lineHeight: 1.9,
  contentWidth: "wide",
  showParagraphIds: false,
  setTheme: (theme) => set({ theme }),
  setDemo: (demo) => set({ demo }),
  setReading: (fontSize, lineHeight) => set({ fontSize, lineHeight }),
  setContentWidth: (contentWidth) => set({ contentWidth }),
  setShowParagraphIds: (showParagraphIds) => set({ showParagraphIds }),
}));
