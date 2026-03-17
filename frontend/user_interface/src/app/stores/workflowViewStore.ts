import { create } from "zustand";

type WorkflowView = "gallery" | "canvas";

type WorkflowViewStore = {
  view: WorkflowView;
  quickSwitcherOpen: boolean;
  setView: (view: WorkflowView) => void;
  openQuickSwitcher: () => void;
  closeQuickSwitcher: () => void;
  /** Callback set by app shell to send a message to chat and close the overlay. */
  runInChat: ((message: string) => void) | null;
  setRunInChat: (fn: ((message: string) => void) | null) => void;
};

export const useWorkflowViewStore = create<WorkflowViewStore>((set) => ({
  view: "gallery",
  quickSwitcherOpen: false,
  setView: (view) => set({ view }),
  openQuickSwitcher: () => set({ quickSwitcherOpen: true }),
  closeQuickSwitcher: () => set({ quickSwitcherOpen: false }),
  runInChat: null,
  setRunInChat: (fn) => set({ runInChat: fn }),
}));
