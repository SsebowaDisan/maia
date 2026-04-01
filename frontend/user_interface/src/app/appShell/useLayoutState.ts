import { useEffect, useRef, useState } from "react";
import {
  CENTER_PANEL_MIN,
  LEFT_PANEL_MIN,
  RIGHT_PANEL_MIN,
  STORAGE_KEYS,
} from "./constants";
import { clamp, readStoredText, readStoredWidth } from "./storage";
import type { ResizeSide, WorkspaceTab } from "./types";

const WORKSPACE_TABS: WorkspaceTab[] = ["Chat", "Files", "Resources", "Settings", "Help"];
const SETTINGS_TABS = new Set(["general", "models", "access"]);
const WORKSPACE_VIEW_PARAM = "view";
const WORKSPACE_TAB_BY_QUERY: Record<string, WorkspaceTab> = {
  chat: "Chat",
  files: "Files",
  resources: "Resources",
  settings: "Settings",
  help: "Help",
};

function readWorkspaceTabFromUrl(): WorkspaceTab | null {
  if (typeof window === "undefined") {
    return null;
  }
  const params = new URLSearchParams(window.location.search);
  const viewValue = String(params.get(WORKSPACE_VIEW_PARAM) || "")
    .trim()
    .toLowerCase();
  if (viewValue && WORKSPACE_TAB_BY_QUERY[viewValue]) {
    return WORKSPACE_TAB_BY_QUERY[viewValue];
  }
  const settingsTab = String(params.get("tab") || "")
    .trim()
    .toLowerCase();
  if (settingsTab === "apis") {
    // Legacy compatibility: old settings URLs still resolve to Settings.
    return "Settings";
  }
  if (SETTINGS_TABS.has(settingsTab)) {
    return "Settings";
  }
  return null;
}

function readStoredActiveTab(): WorkspaceTab {
  const tabFromUrl = readWorkspaceTabFromUrl();
  if (tabFromUrl) {
    return tabFromUrl;
  }
  const raw = readStoredText(STORAGE_KEYS.activeTab, "Chat");
  return WORKSPACE_TABS.includes(raw as WorkspaceTab) ? (raw as WorkspaceTab) : "Chat";
}

function syncWorkspaceTabInUrl(activeTab: WorkspaceTab) {
  if (typeof window === "undefined") {
    return;
  }
  const params = new URLSearchParams(window.location.search);
  const nextValue = activeTab.toLowerCase();
  if (params.get(WORKSPACE_VIEW_PARAM) === nextValue) {
    return;
  }
  params.set(WORKSPACE_VIEW_PARAM, nextValue);
  const nextSearch = params.toString();
  const nextUrl = `${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`;
  window.history.replaceState({}, "", nextUrl);
}

export function useLayoutState() {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() => readStoredActiveTab());
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isInfoPanelOpen, setIsInfoPanelOpen] = useState(true);
  const [sidebarWidth, setSidebarWidth] = useState(() =>
    readStoredWidth(STORAGE_KEYS.sidebarWidth, 300),
  );
  const [infoPanelWidth, setInfoPanelWidth] = useState(() =>
    readStoredWidth(STORAGE_KEYS.infoPanelWidth, 340),
  );
  const [resizeSide, setResizeSide] = useState<ResizeSide>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.activeTab, activeTab);
    syncWorkspaceTabInUrl(activeTab);
  }, [activeTab]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.sidebarWidth, String(Math.round(sidebarWidth)));
  }, [sidebarWidth]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(STORAGE_KEYS.infoPanelWidth, String(Math.round(infoPanelWidth)));
  }, [infoPanelWidth]);

  useEffect(() => {
    const layout = layoutRef.current;
    if (!layout) {
      return;
    }
    const bounds = layout.getBoundingClientRect();
    const availableWidth = bounds.width;
    const leftMax = Math.max(
      LEFT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
    );
    const rightMax = Math.max(
      RIGHT_PANEL_MIN,
      availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
    );
    const nextLeft = clamp(sidebarWidth, LEFT_PANEL_MIN, leftMax);
    const nextRight = clamp(infoPanelWidth, RIGHT_PANEL_MIN, rightMax);
    if (nextLeft !== sidebarWidth) {
      setSidebarWidth(nextLeft);
    }
    if (nextRight !== infoPanelWidth) {
      setInfoPanelWidth(nextRight);
    }
  }, [isInfoPanelOpen, isSidebarCollapsed, sidebarWidth, infoPanelWidth]);

  useEffect(() => {
    if (!resizeSide) {
      return;
    }

    const onMove = (event: MouseEvent) => {
      if ((event.buttons & 1) !== 1) {
        setResizeSide(null);
        return;
      }
      const layout = layoutRef.current;
      if (!layout) {
        return;
      }
      const bounds = layout.getBoundingClientRect();
      const availableWidth = bounds.width;
      if (resizeSide === "left" && !isSidebarCollapsed) {
        const maxLeft = Math.max(
          LEFT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isInfoPanelOpen ? infoPanelWidth : 0),
        );
        const proposed = event.clientX - bounds.left;
        setSidebarWidth(clamp(proposed, LEFT_PANEL_MIN, maxLeft));
      }
      if (resizeSide === "right" && isInfoPanelOpen) {
        const maxRight = Math.max(
          RIGHT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
        );
        const proposed = bounds.right - event.clientX;
        setInfoPanelWidth(clamp(proposed, RIGHT_PANEL_MIN, maxRight));
      }
    };

    const onStop = () => setResizeSide(null);
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") {
        onStop();
      }
    };
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    window.addEventListener("mouseleave", onStop);
    window.addEventListener("blur", onStop);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
      window.removeEventListener("mouseleave", onStop);
      window.removeEventListener("blur", onStop);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [resizeSide, isInfoPanelOpen, isSidebarCollapsed, infoPanelWidth, sidebarWidth]);

  return {
    activeTab,
    infoPanelWidth,
    isInfoPanelOpen,
    isSidebarCollapsed,
    layoutRef,
    resizeSide,
    setActiveTab,
    setIsInfoPanelOpen,
    setIsSidebarCollapsed,
    setResizeSide,
    sidebarWidth,
  };
}
