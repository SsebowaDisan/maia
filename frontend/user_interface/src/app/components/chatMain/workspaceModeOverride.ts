type RuntimeWorkspaceMode = "fast" | "balanced" | "full_theatre";

const WORKSPACE_RENDER_MODE_STORAGE_KEY = "maia.info-panel.workspace-render-mode.v1";

function normalizeRuntimeWorkspaceMode(raw: unknown): RuntimeWorkspaceMode {
  const value = String(raw || "").trim().toLowerCase();
  if (value === "fast") {
    return "fast";
  }
  if (value === "full" || value === "full_theatre") {
    return "full_theatre";
  }
  return "balanced";
}

function readRuntimeWorkspaceMode(): RuntimeWorkspaceMode {
  if (typeof window === "undefined") {
    return "balanced";
  }
  return normalizeRuntimeWorkspaceMode(
    window.localStorage.getItem(WORKSPACE_RENDER_MODE_STORAGE_KEY) || "",
  );
}

function buildWorkspaceModeOverride(): Record<string, unknown> {
  return {
    __workspace_render_mode: readRuntimeWorkspaceMode(),
  };
}

export { buildWorkspaceModeOverride, normalizeRuntimeWorkspaceMode };
export type { RuntimeWorkspaceMode };
