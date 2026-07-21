import { create } from "zustand";

const STORAGE_KEY = "storylens.onboarding.v1";

export type OnboardingStatus = "pending" | "completed" | "skipped";

function readStored(): OnboardingStatus {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === "completed" || raw === "skipped") return raw;
  } catch {
    /* ignore */
  }
  return "pending";
}

function writeStored(status: OnboardingStatus) {
  try {
    localStorage.setItem(STORAGE_KEY, status);
  } catch {
    /* ignore */
  }
}

type State = {
  status: OnboardingStatus;
  complete: () => void;
  skip: () => void;
};

export const useOnboardingStore = create<State>((set) => ({
  status: typeof window !== "undefined" ? readStored() : "pending",
  complete: () => {
    writeStored("completed");
    set({ status: "completed" });
  },
  skip: () => {
    writeStored("skipped");
    set({ status: "skipped" });
  },
}));
