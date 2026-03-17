export type AppPageRouteKey =
  | "admin_review"
  | "marketplace"
  | "my_agents"
  | "workspace"
  | "connectors"
  | "developer"
  | "developer_docs"
  | "agent_builder"
  | "agent_detail"
  | "agent_run"
  | "agent_edit"
  | "marketplace_agent_detail"
  | "connector_marketplace"
  | "operations"
  | "workflow_builder";

type AppRouteParams = {
  agentId?: string;
};

export type AppRouteShell =
  | { kind: "main" }
  | {
      kind: "page";
      key: AppPageRouteKey;
      path: string;
      params?: AppRouteParams;
    }
  | {
      kind: "placeholder";
      key: string;
      title: string;
      description: string;
      path: string;
    };

function normalizePath(pathname: string): string {
  const cleaned = String(pathname || "/").trim();
  if (!cleaned) {
    return "/";
  }
  return cleaned.length > 1 ? cleaned.replace(/\/+$/, "") : cleaned;
}

export function resolveAppRouteShell(pathname: string): AppRouteShell {
  const rawPath = normalizePath(pathname);
  const normalized = rawPath.toLowerCase();
  if (normalized === "/" || normalized === "/chat") {
    return { kind: "main" };
  }
  if (normalized === "/marketplace") {
    return {
      kind: "page",
      key: "marketplace",
      path: "/marketplace",
    };
  }
  if (normalized === "/admin/review") {
    return {
      kind: "page",
      key: "admin_review",
      path: "/admin/review",
    };
  }
  if (normalized === "/workspace") {
    return {
      kind: "page",
      key: "workspace",
      path: "/workspace",
    };
  }
  if (normalized === "/agents") {
    return {
      kind: "page",
      key: "my_agents",
      path: "/agents",
    };
  }
  if (normalized === "/connectors") {
    return {
      kind: "page",
      key: "connectors",
      path: "/connectors",
    };
  }
  if (normalized === "/developer") {
    return {
      kind: "page",
      key: "developer",
      path: "/developer",
    };
  }
  if (normalized === "/developer/docs") {
    return {
      kind: "page",
      key: "developer_docs",
      path: "/developer/docs",
    };
  }
  if (normalized === "/agent-builder") {
    return {
      kind: "page",
      key: "agent_builder",
      path: "/agent-builder",
    };
  }
  if (normalized === "/connector-marketplace") {
    return {
      kind: "page",
      key: "connector_marketplace",
      path: "/connector-marketplace",
    };
  }
  if (normalized === "/operations") {
    return {
      kind: "page",
      key: "operations",
      path: "/operations",
    };
  }
  if (normalized === "/workflow-builder") {
    return {
      kind: "page",
      key: "workflow_builder",
      path: "/workflow-builder",
    };
  }
  if (normalized.startsWith("/marketplace/agents/")) {
    const agentId = decodeURIComponent(rawPath.slice("/marketplace/agents/".length)).trim();
    return {
      kind: "page",
      key: "marketplace_agent_detail",
      path: pathname || "/marketplace/agents/:agentId",
      params: {
        agentId: agentId || undefined,
      },
    };
  }
  if (normalized.startsWith("/agents/") && normalized.endsWith("/run")) {
    const rawAgentId = rawPath
      .slice("/agents/".length, Math.max("/agents/".length, rawPath.length - "/run".length))
      .replace(/\/+$/, "");
    const agentId = decodeURIComponent(rawAgentId).trim();
    return {
      kind: "page",
      key: "agent_run",
      path: pathname || "/agents/:agentId/run",
      params: {
        agentId: agentId || undefined,
      },
    };
  }
  if (normalized.startsWith("/agents/") && normalized.endsWith("/edit")) {
    const rawAgentId = rawPath
      .slice("/agents/".length, Math.max("/agents/".length, rawPath.length - "/edit".length))
      .replace(/\/+$/, "");
    const agentId = decodeURIComponent(rawAgentId).trim();
    return {
      kind: "page",
      key: "agent_edit",
      path: pathname || "/agents/:agentId/edit",
      params: {
        agentId: agentId || undefined,
      },
    };
  }
  if (normalized.startsWith("/agents/")) {
    const agentId = decodeURIComponent(rawPath.slice("/agents/".length)).trim();
    return {
      kind: "page",
      key: "agent_detail",
      path: pathname || "/agents/:agentId",
      params: {
        agentId: agentId || undefined,
      },
    };
  }
  return {
    kind: "placeholder",
    key: "not_found",
    title: "Page Not Found",
    description: "This route is not mapped yet.",
    path: pathname || "/",
  };
}
