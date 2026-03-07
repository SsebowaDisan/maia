export type WorkspaceRenderMode = "fast" | "balanced" | "full";

const RENDER_MODE_STORAGE_KEY = "maia.info-panel.workspace-render-mode.v1";

function normalizeWorkspaceRenderMode(raw: unknown): WorkspaceRenderMode {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "fast") {
    return "fast";
  }
  if (value === "full") {
    return "full";
  }
  return "balanced";
}

function readWorkspaceRenderMode(): WorkspaceRenderMode {
  if (typeof window === "undefined") {
    return "balanced";
  }
  return normalizeWorkspaceRenderMode(window.localStorage.getItem(RENDER_MODE_STORAGE_KEY));
}

function writeWorkspaceRenderMode(mode: WorkspaceRenderMode): void {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(RENDER_MODE_STORAGE_KEY, mode);
}

export {
  normalizeWorkspaceRenderMode,
  readWorkspaceRenderMode,
  writeWorkspaceRenderMode,
};
