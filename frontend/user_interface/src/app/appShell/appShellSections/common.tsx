import { WorkflowHeaderFields } from "../../components/workflowCanvas/WorkflowHeaderFields";
import { resolveAppRouteShell } from "../routeShells";
import { useWorkflowViewStore } from "../../stores/workflowViewStore";

type MindmapNodeFollowUpDraft = {
  nodeId: string;
  title: string;
  text: string;
  pageRef?: string;
  sourceId?: string;
  sourceName?: string;
  defaultPrompt: string;
};

type SidebarOverlayKey =
  | "admin_review"
  | "connectors"
  | "my_agents"
  | "workspace"
  | "marketplace"
  | "workflow_builder"
  | "operations";

type SidebarOverlayConfig = {
  key: SidebarOverlayKey;
  path: string;
  title: string;
  subtitle: string;
};

const SIDEBAR_OVERLAY_BY_PATH: Record<string, SidebarOverlayConfig> = {
  "/admin/review": {
    key: "admin_review",
    path: "/admin/review",
    title: "Review Queue",
    subtitle: "Review pending submissions and approve or reject marketplace agents.",
  },
  "/connectors": {
    key: "connectors",
    path: "/connectors",
    title: "Connectors",
    subtitle: "Manage integration credentials, health, and permissions without leaving chat.",
  },
  "/settings": {
    key: "connectors",
    path: "/connectors",
    title: "Settings",
    subtitle: "Manage integrations and connector settings.",
  },
  "/workspace": {
    key: "workspace",
    path: "/workspace",
    title: "Agents",
    subtitle: "Inspect agent runs, updates, and memory context while staying in the same session.",
  },
  "/agents": {
    key: "my_agents",
    path: "/agents",
    title: "My Agents",
    subtitle: "Review installed agents, statuses, and jump to chat-ready actions.",
  },
  "/workflow-builder": {
    key: "workflow_builder",
    path: "/workflow-builder",
    title: "Workflows",
    subtitle: "Compose multi-agent flows and preview orchestration in one canvas.",
  },
  "/operations": {
    key: "operations",
    path: "/operations",
    title: "Operations",
    subtitle: "Track run reliability, budgets, and system health in real time.",
  },
};

function resolveSidebarOverlayForPath(path: string): SidebarOverlayConfig | null {
  const normalizedPath = String(path || "/").trim().toLowerCase();
  return SIDEBAR_OVERLAY_BY_PATH[normalizedPath] || null;
}

function resolveOverlayReturnPath(search: string): string | null {
  const params = new URLSearchParams(String(search || ""));
  const raw = String(params.get("from") || "").trim();
  if (!raw) {
    return null;
  }
  const candidate = raw.startsWith("/") ? raw : `/${raw}`;
  const route = resolveAppRouteShell(candidate);
  if (route.kind !== "page") {
    return null;
  }
  return route.path;
}

function WorkflowBuilderHeaderActions() {
  const view = useWorkflowViewStore((s) => s.view);
  const setView = useWorkflowViewStore((s) => s.setView);
  if (view === "gallery") {
    return null;
  }
  return <WorkflowHeaderFields onBackToGallery={() => setView("gallery")} />;
}

export {
  SIDEBAR_OVERLAY_BY_PATH,
  WorkflowBuilderHeaderActions,
  resolveOverlayReturnPath,
  resolveSidebarOverlayForPath,
};
export type { MindmapNodeFollowUpDraft, SidebarOverlayConfig, SidebarOverlayKey };
