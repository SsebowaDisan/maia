import React from "react";
import { MousePointer2 } from "lucide-react";
import { resolveTheatreTheme } from "../theme";
import type { TheatreThemeOverride } from "../theme";

export interface TheatreDesktopProps {
  fullscreen?: boolean;
  streaming?: boolean;
  isTheaterView?: boolean;
  isFocusMode?: boolean;
  title?: string;
  roleLabel?: string;
  statusText?: string;
  sceneTransitionLabel?: string;
  className?: string;
  showTheaterToggle?: boolean;
  onToggleTheaterView?: () => void;
  onToggleFocusMode?: () => void;
  onOpenFullscreen?: () => void;
  cursorPoint?: { x: number; y: number } | null;
  showCursor?: boolean;
  viewportOverlay?: React.ReactNode;
  footer?: React.ReactNode;
  captionTitle?: string;
  captionDetail?: string;
  showCaption?: boolean;
  children: React.ReactNode;
  theme?: TheatreThemeOverride;
}

export function TheatreDesktop({
  fullscreen = false,
  streaming = false,
  isTheaterView = true,
  isFocusMode = true,
  title = "Agent desktop",
  roleLabel = "",
  statusText = "",
  sceneTransitionLabel = "",
  className = "",
  showTheaterToggle = true,
  onToggleTheaterView,
  onToggleFocusMode,
  onOpenFullscreen,
  cursorPoint = null,
  showCursor = false,
  viewportOverlay = null,
  footer = null,
  captionTitle = "",
  captionDetail = "",
  showCaption = false,
  children,
  theme,
}: TheatreDesktopProps) {
  const resolvedTheme = resolveTheatreTheme(theme);
  const viewerHeightClass = fullscreen
    ? isFocusMode
      ? resolvedTheme.desktop.viewportFrameFocusHeight
      : resolvedTheme.desktop.viewportFrameFullscreenHeight
    : isTheaterView
      ? resolvedTheme.desktop.viewportFrameInlineHeight
      : resolvedTheme.desktop.viewportFrameCompactHeight;
  const viewerWidthClass = fullscreen
    ? resolvedTheme.desktop.viewportFullscreenWidth
    : isTheaterView
      ? resolvedTheme.desktop.viewportTheatreWidth
      : resolvedTheme.desktop.viewportStandardWidth;

  return (
    <div
      className={`${resolvedTheme.desktop.shell} ${fullscreen ? "mb-0" : ""} ${className}`}
    >
      <div className={resolvedTheme.desktop.metaRow}>
        <span className={resolvedTheme.desktop.metaLabel}>
          <span className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-[4px] border border-current/15 text-[9px]">
            D
          </span>
          {title}
          {roleLabel ? (
            <span className={resolvedTheme.desktop.metaRole}>| {roleLabel}</span>
          ) : null}
        </span>
        <div className={resolvedTheme.desktop.controlsWrap}>
          {!fullscreen && showTheaterToggle ? (
            <button
              type="button"
              onClick={onToggleTheaterView}
              className={resolvedTheme.desktop.controlButton}
              title={isTheaterView ? "Switch to standard viewer size" : "Switch to theatre viewer size"}
            >
              {isTheaterView ? "Theatre" : "Standard"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={fullscreen ? onToggleFocusMode : onOpenFullscreen}
            className={resolvedTheme.desktop.controlButton}
            title={fullscreen ? "Toggle focus mode" : "Open fullscreen viewer"}
          >
            {fullscreen ? (isFocusMode ? "Focus on" : "Focus off") : "Fullscreen"}
          </button>
          <span className={resolvedTheme.desktop.liveChip}>
            {streaming ? <span className={resolvedTheme.desktop.liveDot} /> : null}
            {streaming ? "Live" : "Replay"}
          </span>
        </div>
      </div>

      {statusText ? <p className={resolvedTheme.desktop.statusText}>{statusText}</p> : null}

      <div className={`${resolvedTheme.desktop.viewportWrap} ${viewerWidthClass}`}>
        <div className={`${resolvedTheme.desktop.viewportPanel} ${viewerHeightClass}`}>
          <div className={resolvedTheme.desktop.viewportFrame}>{children}</div>

          {sceneTransitionLabel ? (
            <div className={resolvedTheme.desktop.stageBadge}>{sceneTransitionLabel}</div>
          ) : null}

          {viewportOverlay}

          {showCursor && cursorPoint ? (
            <div
              className={resolvedTheme.desktop.cursor}
              style={{ left: `${cursorPoint.x}%`, top: `${cursorPoint.y}%` }}
            >
              <MousePointer2 className="h-4 w-4 -translate-x-1/2 -translate-y-1/2" />
            </div>
          ) : null}

          {showCaption ? (
            <div className={resolvedTheme.desktop.captionWrap}>
              <div className={resolvedTheme.desktop.captionCard}>
                {captionTitle ? (
                  <p className={resolvedTheme.desktop.captionTitle}>{captionTitle}</p>
                ) : null}
                {captionDetail ? (
                  <p className={resolvedTheme.desktop.captionDetail}>{captionDetail}</p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      {footer}
    </div>
  );
}

