import { create } from "zustand";

const STORAGE_KEY = "storylens.showAdvancedSettings";

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
  showAdvancedSettings: boolean;
  setShowAdvancedSettings: (enabled: boolean) => void;
};

export const useAdvancedSettingsStore = create<State>((set) => ({
  showAdvancedSettings: typeof window !== "undefined" ? readStored() : false,
  setShowAdvancedSettings: (enabled) => {
    writeStored(enabled);
    set({ showAdvancedSettings: enabled });
  },
}));
