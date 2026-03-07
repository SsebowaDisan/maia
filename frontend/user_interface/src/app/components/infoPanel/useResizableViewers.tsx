import { useEffect, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";

type ViewerHeightKey = "mindmap" | "citation";

type ViewerHeights = {
  mindmap: number;
  citation: number;
};

const VIEWER_HEIGHT_STORAGE_KEY = "maia.info-panel.viewer-heights.v2";
const DEFAULT_VIEWER_HEIGHTS: ViewerHeights = {
  mindmap: 520,
  citation: 420,
};
const VIEWER_HEIGHT_LIMITS: Record<ViewerHeightKey, { min: number; max: number }> = {
  mindmap: { min: 260, max: 1000 },
  citation: { min: 220, max: 1000 },
};

function clampViewerHeight(viewer: ViewerHeightKey, rawValue: unknown): number {
  const limits = VIEWER_HEIGHT_LIMITS[viewer];
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_VIEWER_HEIGHTS[viewer];
  }
  return Math.max(limits.min, Math.min(limits.max, Math.round(parsed)));
}

function loadViewerHeights(): ViewerHeights {
  if (typeof window === "undefined") {
    return { ...DEFAULT_VIEWER_HEIGHTS };
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(VIEWER_HEIGHT_STORAGE_KEY) || "{}") as
      | Partial<ViewerHeights>
      | null;
    return {
      mindmap: clampViewerHeight("mindmap", parsed?.mindmap),
      citation: clampViewerHeight("citation", parsed?.citation),
    };
  } catch {
    return { ...DEFAULT_VIEWER_HEIGHTS };
  }
}

function useResizableViewers() {
  const [viewerHeights, setViewerHeights] = useState<ViewerHeights>(() => loadViewerHeights());
  const dragViewerRef = useRef<ViewerHeightKey | null>(null);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);
  const dragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(VIEWER_HEIGHT_STORAGE_KEY, JSON.stringify(viewerHeights));
  }, [viewerHeights]);

  const setViewerHeight = (viewer: ViewerHeightKey, value: unknown) => {
    setViewerHeights((previous) => {
      const nextValue = clampViewerHeight(viewer, value);
      if (previous[viewer] === nextValue) {
        return previous;
      }
      return { ...previous, [viewer]: nextValue };
    });
  };

  const beginViewerResize = (viewer: ViewerHeightKey, event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragCleanupRef.current) {
      dragCleanupRef.current();
      dragCleanupRef.current = null;
    }
    dragViewerRef.current = viewer;
    dragStartYRef.current = event.clientY;
    dragStartHeightRef.current = viewerHeights[viewer];

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: MouseEvent) => {
      const activeViewer = dragViewerRef.current;
      if (!activeViewer) {
        return;
      }
      if ((moveEvent.buttons & 1) !== 1) {
        onStop();
        return;
      }
      const deltaY = moveEvent.clientY - dragStartYRef.current;
      setViewerHeight(activeViewer, dragStartHeightRef.current + deltaY);
    };

    const onStop = () => {
      dragViewerRef.current = null;
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
      window.removeEventListener("mouseleave", onStop);
      window.removeEventListener("blur", onStop);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (dragCleanupRef.current === onStop) {
        dragCleanupRef.current = null;
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") {
        onStop();
      }
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    window.addEventListener("mouseleave", onStop);
    window.addEventListener("blur", onStop);
    document.addEventListener("visibilitychange", onVisibilityChange);
    dragCleanupRef.current = onStop;
  };

  useEffect(
    () => () => {
      if (dragCleanupRef.current) {
        dragCleanupRef.current();
        dragCleanupRef.current = null;
      }
    },
    [],
  );

  const renderViewerResizeHandle = (viewer: ViewerHeightKey, label: string) => {
    return (
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label={`Resize ${label} viewer`}
        onMouseDown={(mouseEvent) => beginViewerResize(viewer, mouseEvent)}
        className="group relative mt-2 h-3 cursor-row-resize select-none"
      >
        <div className="absolute left-1/2 top-1/2 h-[2px] w-16 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/15 transition-colors group-hover:bg-[#2f2f34]/60" />
      </div>
    );
  };

  return {
    viewerHeights,
    renderViewerResizeHandle,
  };
}

export { useResizableViewers };
