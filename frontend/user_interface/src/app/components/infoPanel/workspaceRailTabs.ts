export type WorkspaceRailTab = "work_graph" | "theatre" | "evidence" | "artifacts";

type WorkspaceRailTabMeta = {
  id: WorkspaceRailTab;
  label: string;
};

const WORKSPACE_RAIL_TABS: WorkspaceRailTabMeta[] = [
  { id: "work_graph", label: "Work Graph" },
  { id: "theatre", label: "Theatre" },
  { id: "evidence", label: "Evidence" },
  { id: "artifacts", label: "Artifacts" },
];

function normalizeWorkspaceRailTab(raw: unknown): WorkspaceRailTab {
  const normalized = String(raw || "").trim().toLowerCase();
  for (const row of WORKSPACE_RAIL_TABS) {
    if (row.id === normalized) {
      return row.id;
    }
  }
  return "evidence";
}

export { WORKSPACE_RAIL_TABS, normalizeWorkspaceRailTab };
