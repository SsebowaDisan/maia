import { Monitor, MousePointer2 } from "lucide-react";
import { AgentDesktopScene } from "../AgentDesktopScene";

interface DesktopViewerProps {
  fullscreen?: boolean;
  streaming: boolean;
  isTheaterView: boolean;
  isFocusMode: boolean;
  onToggleTheaterView: () => void;
  onToggleFocusMode: () => void;
  onOpenFullscreen: () => void;
  desktopStatus: string;
  sceneTransitionLabel: string;
  safeCursor: number;
  totalEvents: number;
  activeTitle: string;
  activeDetail: string;
  sceneText: string;
  cursorLabel: string;
  stageFileName: string;
  eventCursor: { x: number; y: number } | null;
  cursorPoint: { x: number; y: number };
  effectiveSnapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isDocsScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  canRenderPdfFrame: boolean;
  stageFileUrl: string;
  browserUrl: string;
  emailRecipient: string;
  emailSubject: string;
  emailBodyHint: string;
  docBodyHint: string;
  sheetBodyHint: string;
  activeEventType: string;
  activeSceneData: Record<string, unknown>;
  sceneDocumentUrl: string;
  sceneSpreadsheetUrl: string;
  onSnapshotError: () => void;
}

function DesktopViewer({
  fullscreen = false,
  streaming,
  isTheaterView,
  isFocusMode,
  onToggleTheaterView,
  onToggleFocusMode,
  onOpenFullscreen,
  desktopStatus,
  sceneTransitionLabel,
  safeCursor,
  totalEvents,
  activeTitle,
  activeDetail,
  sceneText,
  cursorLabel,
  stageFileName,
  eventCursor,
  cursorPoint,
  effectiveSnapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  canRenderPdfFrame,
  stageFileUrl,
  browserUrl,
  emailRecipient,
  emailSubject,
  emailBodyHint,
  docBodyHint,
  sheetBodyHint,
  activeEventType,
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  onSnapshotError,
}: DesktopViewerProps) {
  const inlineViewerHeightClass = isTheaterView
    ? "h-[380px] md:h-[500px] xl:h-[600px]"
    : "h-[220px] md:h-[280px]";
  const fullscreenViewerHeightClass = isFocusMode ? "h-[calc(100vh-160px)]" : "h-[74vh]";
  const viewerHeightClass = fullscreen ? fullscreenViewerHeightClass : inlineViewerHeightClass;

  return (
    <div
      className={`mb-3 rounded-2xl border border-black/[0.06] bg-[#0f1115] p-3 text-white shadow-inner ${
        fullscreen ? "mb-0" : ""
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-white/75">
        <span className="inline-flex items-center gap-1.5">
          <Monitor className="h-3.5 w-3.5" />
          Agent desktop
        </span>
        <div className="inline-flex items-center gap-2">
          {!fullscreen ? (
            <button
              type="button"
              onClick={onToggleTheaterView}
              className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
              title={isTheaterView ? "Switch to standard viewer size" : "Switch to theater viewer size"}
            >
              {isTheaterView ? "THEATER" : "STANDARD"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={fullscreen ? onToggleFocusMode : onOpenFullscreen}
            className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
            title={fullscreen ? "Toggle focus mode" : "Open fullscreen viewer"}
          >
            {fullscreen ? (isFocusMode ? "FOCUS: ON" : "FOCUS: OFF") : "FULLSCREEN"}
          </button>
          <span className="rounded-full border border-white/20 px-2 py-0.5">
            {streaming ? "LIVE" : "REPLAY"}
          </span>
        </div>
      </div>

      <p className="mb-2 text-[13px] font-medium text-white">{desktopStatus}</p>

      <div
        className={`relative overflow-hidden rounded-xl border border-white/15 bg-[linear-gradient(180deg,#11141b_0%,#0a0c11_100%)] ${viewerHeightClass}`}
      >
        <div className="absolute inset-0">
          <AgentDesktopScene
            snapshotUrl={effectiveSnapshotUrl}
            isBrowserScene={isBrowserScene}
            isEmailScene={isEmailScene}
            isDocumentScene={isDocumentScene}
            isDocsScene={isDocsScene}
            isSheetsScene={isSheetsScene}
            isSystemScene={isSystemScene}
            canRenderPdfFrame={canRenderPdfFrame}
            stageFileUrl={stageFileUrl}
            stageFileName={stageFileName}
            browserUrl={browserUrl}
            emailRecipient={emailRecipient}
            emailSubject={emailSubject}
            emailBodyHint={emailBodyHint}
            docBodyHint={docBodyHint}
            sheetBodyHint={sheetBodyHint}
            sceneText={sceneText}
            activeTitle={activeTitle}
            activeDetail={activeDetail}
            activeEventType={activeEventType}
            activeSceneData={activeSceneData}
            sceneDocumentUrl={sceneDocumentUrl}
            sceneSpreadsheetUrl={sceneSpreadsheetUrl}
            onSnapshotError={onSnapshotError}
          />
        </div>
        {sceneTransitionLabel && !(fullscreen && isFocusMode) ? (
          <div className="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full border border-white/20 bg-black/58 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-white/85 backdrop-blur-sm">
            {sceneTransitionLabel}
          </div>
        ) : null}

        {eventCursor && !(fullscreen && isFocusMode) ? (
          <>
            <div
              className="pointer-events-none absolute left-0 right-0 h-px bg-white/25"
              style={{ top: `${cursorPoint.y}%` }}
            />
            <div
              className="pointer-events-none absolute z-20 transition-all duration-300"
              style={{ left: `${cursorPoint.x}%`, top: `${cursorPoint.y}%` }}
            >
              <div className="relative">
                <MousePointer2 className="h-4 w-4 -translate-x-1/2 -translate-y-1/2 text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.65)]" />
              </div>
            </div>
          </>
        ) : null}
        {!(fullscreen && isFocusMode) ? (
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent" />
        ) : null}

        {activeTitle && !(fullscreen && isFocusMode) ? (
          <div className="pointer-events-none absolute inset-x-3 bottom-3 z-30">
            <div className="rounded-xl border border-white/20 bg-black/55 px-3 py-2 backdrop-blur-md">
              <div className="mb-1 flex items-center justify-between gap-2 text-[10px] uppercase tracking-[0.08em] text-white/70">
                <span>{streaming ? "Live scene" : "Current scene"}</span>
                <span className="inline-flex items-center gap-1">
                  {streaming ? <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> : null}
                  Step {safeCursor + 1}/{totalEvents}
                </span>
              </div>
              <p className="truncate text-[13px] font-semibold text-white">{activeTitle}</p>
              <p className="mt-0.5 line-clamp-2 text-[11px] text-white/85">
                {sceneText || activeDetail || "Processing..."}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {!(fullscreen && isFocusMode) ? (
        <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-white/70">
          <span className="truncate">Opened: {stageFileName}</span>
          <span className="truncate text-right">{cursorLabel}</span>
        </div>
      ) : null}
    </div>
  );
}

export { DesktopViewer };
