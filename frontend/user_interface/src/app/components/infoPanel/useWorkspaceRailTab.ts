import { useEffect, useState } from "react";

import { normalizeWorkspaceRailTab, type WorkspaceRailTab } from "./workspaceRailTabs";

const STORAGE_KEY = "maia.info-panel.workspace-tabs.v1";
const TAB_QUERY_PARAM = "workspace_tab";

function readTabPreferences(): Record<string, WorkspaceRailTab> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "{}") as Record<string, unknown>;
    const next: Record<string, WorkspaceRailTab> = {};
    for (const [conversationId, raw] of Object.entries(parsed || {})) {
      next[conversationId] = normalizeWorkspaceRailTab(raw);
    }
    return next;
  } catch {
    return {};
  }
}

function writeTabPreference(conversationId: string, tab: WorkspaceRailTab): void {
  if (typeof window === "undefined") {
    return;
  }
  const key = String(conversationId || "").trim();
  if (!key) {
    return;
  }
  const current = readTabPreferences();
  current[key] = tab;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
}

function readTabFromUrl(): WorkspaceRailTab | null {
  if (typeof window === "undefined") {
    return null;
  }
  const params = new URLSearchParams(window.location.search || "");
  const raw = params.get(TAB_QUERY_PARAM);
  if (!raw) {
    return null;
  }
  return normalizeWorkspaceRailTab(raw);
}

function writeTabToUrl(tab: WorkspaceRailTab): void {
  if (typeof window === "undefined") {
    return;
  }
  const next = normalizeWorkspaceRailTab(tab);
  const url = new URL(window.location.href);
  url.searchParams.set(TAB_QUERY_PARAM, next);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}

function useWorkspaceRailTab(options: {
  conversationId?: string | null;
  hasMindmapPayload: boolean;
  hasArtifacts: boolean;
  hasTheatreFocus: boolean;
}) {
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<WorkspaceRailTab>(() =>
    normalizeWorkspaceRailTab("evidence"),
  );
  const conversationId = String(options.conversationId || "").trim();

  useEffect(() => {
    const urlTab = readTabFromUrl();
    const storedTab = normalizeWorkspaceRailTab(readTabPreferences()[conversationId] || "evidence");
    const nextTab = normalizeWorkspaceRailTab(urlTab || storedTab);
    setActiveWorkspaceTab(nextTab);
  }, [conversationId]);

  useEffect(() => {
    const onPopState = () => {
      const urlTab = readTabFromUrl();
      if (urlTab) {
        setActiveWorkspaceTab(urlTab);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (activeWorkspaceTab === "work_graph" && !options.hasMindmapPayload) {
      setActiveWorkspaceTab("evidence");
      return;
    }
    if (activeWorkspaceTab === "theatre" && !options.hasTheatreFocus) {
      setActiveWorkspaceTab(options.hasMindmapPayload ? "work_graph" : "evidence");
      return;
    }
    if (activeWorkspaceTab === "artifacts" && !options.hasArtifacts) {
      setActiveWorkspaceTab("evidence");
    }
  }, [
    activeWorkspaceTab,
    options.hasArtifacts,
    options.hasMindmapPayload,
    options.hasTheatreFocus,
  ]);

  const updateTab = (tab: WorkspaceRailTab) => {
    setActiveWorkspaceTab(tab);
    writeTabPreference(conversationId, tab);
    writeTabToUrl(tab);
  };

  return { activeWorkspaceTab, setActiveWorkspaceTab: updateTab };
}

export { useWorkspaceRailTab };
