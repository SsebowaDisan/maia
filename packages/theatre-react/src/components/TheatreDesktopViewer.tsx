import React from "react";
import { TheatreDesktop } from "./TheatreDesktop";

export interface TheatreDesktopViewerProps {
  fullscreen?: boolean;
  streaming: boolean;
  isTheaterView: boolean;
  isFocusMode: boolean;
  onToggleTheaterView: () => void;
  onToggleFocusMode: () => void;
  onOpenFullscreen: () => void;
  desktopStatus: string;
  sceneTransitionLabel: string;
  activeRoleLabel: string;
  roleNarrative: string;
  activeTitle: string;
  activeDetail: string;
  sceneText: string;
  activeEventType: string;
  eventCursor: { x: number; y: number } | null;
  cursorPoint: { x: number; y: number };
  effectiveSnapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isDocsScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  viewportOverlay?: React.ReactNode;
  footer?: React.ReactNode;
  scene: React.ReactNode;
}

function isPlannerNarrativeEventType(eventType: string): boolean {
  const normalized = String(eventType || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized === "planning_started" ||
    normalized.startsWith("plan_") ||
    normalized.startsWith("planning_") ||
    normalized.startsWith("task_understanding_") ||
    normalized.startsWith("preflight_") ||
    normalized.startsWith("llm.task_") ||
    normalized.startsWith("llm.plan_") ||
    normalized === "llm.web_routing_decision" ||
    normalized === "llm.intent_tags"
  );
}

export function TheatreDesktopViewer({
  fullscreen = false,
  streaming,
  isTheaterView,
  isFocusMode,
  onToggleTheaterView,
  onToggleFocusMode,
  onOpenFullscreen,
  desktopStatus,
  sceneTransitionLabel,
  activeRoleLabel,
  roleNarrative,
  activeTitle,
  activeDetail,
  sceneText,
  activeEventType,
  eventCursor,
  cursorPoint,
  effectiveSnapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  viewportOverlay = null,
  footer = null,
  scene,
}: TheatreDesktopViewerProps) {
  const suppressOverlayDetail = isPlannerNarrativeEventType(activeEventType) && !isBrowserScene;
  const shouldRenderCursor = Boolean(eventCursor) && !isBrowserScene;
  const showCaption =
    Boolean(activeTitle) &&
    !(fullscreen && isFocusMode) &&
    !isBrowserScene &&
    !isDocumentScene &&
    !isEmailScene &&
    !isSheetsScene &&
    !isDocsScene &&
    !isSystemScene &&
    !effectiveSnapshotUrl;

  return (
    <TheatreDesktop
      fullscreen={fullscreen}
      streaming={streaming}
      isTheaterView={isTheaterView}
      isFocusMode={isFocusMode}
      roleLabel={activeRoleLabel}
      statusText={roleNarrative || desktopStatus}
      sceneTransitionLabel={sceneTransitionLabel}
      showTheaterToggle={!fullscreen}
      onToggleTheaterView={onToggleTheaterView}
      onToggleFocusMode={onToggleFocusMode}
      onOpenFullscreen={onOpenFullscreen}
      cursorPoint={cursorPoint}
      showCursor={shouldRenderCursor}
      showCaption={showCaption}
      captionTitle={activeTitle}
      captionDetail={suppressOverlayDetail ? "" : sceneText || roleNarrative || activeDetail || "Processing..."}
      viewportOverlay={viewportOverlay}
      footer={footer}
    >
      {scene}
    </TheatreDesktop>
  );
}
