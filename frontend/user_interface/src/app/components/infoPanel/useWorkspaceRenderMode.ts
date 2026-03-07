import { useState } from "react";

import {
  readWorkspaceRenderMode,
  type WorkspaceRenderMode,
  writeWorkspaceRenderMode,
} from "./workspaceRenderModes";

function useWorkspaceRenderMode() {
  const [workspaceRenderMode, setWorkspaceRenderModeState] = useState<WorkspaceRenderMode>(() =>
    readWorkspaceRenderMode(),
  );

  const setWorkspaceRenderMode = (mode: WorkspaceRenderMode) => {
    setWorkspaceRenderModeState(mode);
    writeWorkspaceRenderMode(mode);
  };

  return { workspaceRenderMode, setWorkspaceRenderMode };
}

export { useWorkspaceRenderMode };
