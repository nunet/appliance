// hooks/useAppMode.ts
import { create } from "zustand";
import { persist } from "zustand/middleware";

type AppMode = "simple" | "advanced" | "";

interface AppModeState {
  mode: AppMode;
  setMode: (mode: AppMode) => void;
  toggleMode: () => void;
}

export const useAppMode = create<AppModeState>()(
  persist(
    (set, get) => ({
      mode: "simple", // default
      setMode: (mode) => set({ mode }),
      toggleMode: () =>
        set({ mode: get().mode === "simple" ? "advanced" : "simple" }),
    }),
    {
      name: "app-mode-storage",
      onRehydrateStorage: () => (state) => {
        if (state?.mode === "") {
          state.setMode("simple");
        }
      },
    }
  )
);
