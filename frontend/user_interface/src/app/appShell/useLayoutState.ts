import { useEffect, useRef, useState } from "react";
import {
  CENTER_PANEL_MIN,
  LEFT_PANEL_MAX,
  LEFT_PANEL_MIN,
  RIGHT_PANEL_MAX,
  RIGHT_PANEL_MIN,
  STORAGE_KEYS,
} from "./constants";
import { clamp, readStoredWidth } from "./storage";
import type { ResizeSide, WorkspaceTab } from "./types";

export function useLayoutState() {
  const layoutRef = useRef<HTMLDivElement | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("Chat");
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
    const nextLeft = clamp(sidebarWidth, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, leftMax));
    const nextRight = clamp(infoPanelWidth, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, rightMax));
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
        setSidebarWidth(clamp(proposed, LEFT_PANEL_MIN, Math.min(LEFT_PANEL_MAX, maxLeft)));
      }
      if (resizeSide === "right" && isInfoPanelOpen) {
        const maxRight = Math.max(
          RIGHT_PANEL_MIN,
          availableWidth - CENTER_PANEL_MIN - (isSidebarCollapsed ? 64 : sidebarWidth),
        );
        const proposed = bounds.right - event.clientX;
        setInfoPanelWidth(clamp(proposed, RIGHT_PANEL_MIN, Math.min(RIGHT_PANEL_MAX, maxRight)));
      }
    };

    const onStop = () => setResizeSide(null);
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    return () => {
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
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
