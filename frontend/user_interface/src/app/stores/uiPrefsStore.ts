import { create } from "zustand";
import { persist } from "zustand/middleware";

type UiTheme = "system" | "light" | "dark";
type UiDensity = "comfortable" | "compact";

type UiPrefsStoreState = {
  theme: UiTheme;
  density: UiDensity;
  lastVisitedPath: string;
  setTheme: (theme: UiTheme) => void;
  setDensity: (density: UiDensity) => void;
  setLastVisitedPath: (path: string) => void;
};

const useUiPrefsStore = create<UiPrefsStoreState>()(
  persist(
    (set) => ({
      theme: "system",
      density: "comfortable",
      lastVisitedPath: "/",
      setTheme: (theme) => set({ theme }),
      setDensity: (density) => set({ density }),
      setLastVisitedPath: (path) =>
        set({
          lastVisitedPath: String(path || "/").trim() || "/",
        }),
    }),
    {
      name: "maia.ui.prefs.v1",
      partialize: (state) => ({
        theme: state.theme,
        density: state.density,
        lastVisitedPath: state.lastVisitedPath,
      }),
    },
  ),
);

export { useUiPrefsStore };
export type { UiDensity, UiTheme };

