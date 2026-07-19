import { create } from "zustand";

const STORAGE_KEY = "storylens.developerMode";

function readStored(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStored(enabled: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0");
  } catch {
    /* ignore */
  }
}

type State = {
  developerMode: boolean;
  setDeveloperMode: (enabled: boolean) => void;
  toggleDeveloperMode: () => void;
};

export const useDeveloperModeStore = create<State>((set, get) => ({
  developerMode: typeof window !== "undefined" ? readStored() : false,
  setDeveloperMode: (enabled) => {
    writeStored(enabled);
    set({ developerMode: enabled });
  },
  toggleDeveloperMode: () => {
    const next = !get().developerMode;
    writeStored(next);
    set({ developerMode: next });
  },
}));
