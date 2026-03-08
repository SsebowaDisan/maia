import { Monitor, MousePointer2 } from "lucide-react";
import { AgentDesktopScene } from "../AgentDesktopScene";
import { DiffViewer } from "./DiffViewer";

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
  activeRoleColor: string;
  activeRoleLabel: string;
  roleNarrative: string;
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
  activeRoleColor,
  activeRoleLabel,
  roleNarrative,
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
    ? "h-[clamp(250px,40vh,410px)]"
    : "h-[clamp(200px,28vh,285px)]";
  const fullscreenViewerHeightClass = isFocusMode ? "h-[calc(100vh-180px)]" : "h-[74vh]";
  const viewerHeightClass = fullscreen ? fullscreenViewerHeightClass : inlineViewerHeightClass;
  const viewerWidthClass = fullscreen
    ? "w-full"
    : isTheaterView
      ? "w-full max-w-[860px]"
      : "w-full max-w-[760px]";
  const suppressOverlayDetail = isPlannerNarrativeEventType(activeEventType) && !isBrowserScene;
  const shouldRenderCursor = Boolean(eventCursor) && !isBrowserScene;

  return (
    <div
      className={`mx-auto mb-3 w-full max-w-[920px] rounded-2xl border border-black/[0.06] bg-[#0f1115] p-3 text-white shadow-inner ${
        fullscreen ? "mb-0" : ""
      }`}
    >
      <div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-white/70">
        <span className="inline-flex items-center gap-1.5 text-[11px]">
          <Monitor className="h-3.5 w-3.5" />
          Agent desktop
          {activeRoleLabel ? <span className="text-white/45">· {activeRoleLabel}</span> : null}
        </span>
        <div className="inline-flex items-center gap-2">
          {!fullscreen ? (
            <button
              type="button"
              onClick={onToggleTheaterView}
              className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
              title={isTheaterView ? "Switch to standard viewer size" : "Switch to theater viewer size"}
            >
              {isTheaterView ? "Theatre" : "Standard"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={fullscreen ? onToggleFocusMode : onOpenFullscreen}
            className="rounded-full border border-white/20 px-2 py-0.5 text-[10px] text-white/85 transition hover:bg-white/10"
            title={fullscreen ? "Toggle focus mode" : "Open fullscreen viewer"}
          >
            {fullscreen ? (isFocusMode ? "Focus on" : "Focus off") : "Fullscreen"}
          </button>
          <span className="inline-flex items-center gap-1 rounded-full border border-white/20 px-2 py-0.5">
            {streaming ? <span className="h-1.5 w-1.5 rounded-full bg-[#34c759]" /> : null}
            {streaming ? "Live" : "Replay"}
          </span>
        </div>
      </div>

      <p className="mb-2 text-[12px] font-medium text-white/90">
        {roleNarrative || desktopStatus}
      </p>

      <div className={`mx-auto ${viewerWidthClass}`}>
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
          {activeEventType === "doc_insert_text" && activeSceneData["content_before"] ? (
            <DiffViewer
              before={String(activeSceneData["content_before"] || "")}
              after={String(activeSceneData["content_after"] || "")}
            />
          ) : null}
          {sceneTransitionLabel ? (
            <div className="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full border border-white/16 bg-black/48 px-3 py-1 text-[10px] font-medium tracking-[0.04em] text-white/80 backdrop-blur-sm">
              {sceneTransitionLabel}
            </div>
          ) : null}

          {shouldRenderCursor ? (
            <div
              className="pointer-events-none absolute z-20 transition-all duration-500 ease-out"
              style={{ left: `${cursorPoint.x}%`, top: `${cursorPoint.y}%` }}
            >
              <MousePointer2 className="h-4 w-4 -translate-x-1/2 -translate-y-1/2 text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.65)]" />
            </div>
          ) : null}

          {activeTitle &&
          !(fullscreen && isFocusMode) &&
          !isBrowserScene &&
          !isDocumentScene &&
          !isEmailScene &&
          !isSheetsScene &&
          !isDocsScene &&
          !isSystemScene &&
          !effectiveSnapshotUrl ? (
            <div className="pointer-events-none absolute inset-x-3 bottom-3 z-30">
              <div className="rounded-xl border border-white/18 bg-black/46 px-3 py-2 backdrop-blur-md">
                <p className="truncate text-[13px] font-semibold text-white">{activeTitle}</p>
                {!suppressOverlayDetail ? (
                  <p className="mt-0.5 line-clamp-2 text-[11px] text-white/85">
                    {sceneText || roleNarrative || activeDetail || "Processing..."}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export { DesktopViewer };
