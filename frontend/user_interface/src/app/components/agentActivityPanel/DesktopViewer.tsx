import { Monitor, MousePointer2 } from "lucide-react";
import { AgentDesktopScene } from "../AgentDesktopScene";
import type { InteractionSuggestion } from "./interactionSuggestionMerge";
import { DoneStageOverlay } from "./DoneStageOverlay";
import { DiffViewer } from "./DiffViewer";
import { InteractionSuggestionsPanel } from "./InteractionSuggestionsPanel";

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
  runId: string;
  activeStepIndex: number | null;
  interactionSuggestion: InteractionSuggestion[] | null;
  activeSceneData: Record<string, unknown>;
  sceneDocumentUrl: string;
  sceneSpreadsheetUrl: string;
  computerUseSessionId?: string;
  computerUseTask?: string;
  computerUseModel?: string;
  computerUseMaxIterations?: number | null;
  onSnapshotError: () => void;
  showDoneStage: boolean;
  doneStageTitle: string;
  doneStageDetail: string;
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
  runId,
  activeStepIndex,
  interactionSuggestion,
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  computerUseSessionId = "",
  computerUseTask = "",
  computerUseModel = "",
  computerUseMaxIterations = null,
  onSnapshotError,
  showDoneStage,
  doneStageTitle,
  doneStageDetail,
}: DesktopViewerProps) {
  const inlineViewerHeightClass = isTheaterView
    ? "h-[clamp(460px,72vh,760px)]"
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
      className={`mx-auto mb-3 w-full max-w-[940px] rounded-2xl border border-[#e5e7eb] bg-white p-4 text-[#111827] shadow-[0_16px_36px_-30px_rgba(15,23,42,0.4)] ${
        fullscreen ? "mb-0" : ""
      }`}
    >
      <div className="mb-2.5 flex items-center justify-between gap-2 text-[11px] text-[#6b7280]">
        <span className="inline-flex items-center gap-1.5 text-[11px] text-[#4b5563]">
          <Monitor className="h-3.5 w-3.5" />
          Agent desktop
          {activeRoleLabel ? <span className="text-[#9ca3af]">· {activeRoleLabel}</span> : null}
        </span>
        <div className="inline-flex items-center gap-2">
          {!fullscreen ? (
            <button
              type="button"
              onClick={onToggleTheaterView}
              className="rounded-full border border-[#d7dbe3] bg-[#f8fafc] px-2.5 py-0.5 text-[10px] text-[#4b5563] transition hover:bg-[#eef2f7]"
              title={isTheaterView ? "Switch to standard viewer size" : "Switch to theater viewer size"}
            >
              {isTheaterView ? "Theatre" : "Standard"}
            </button>
          ) : null}
          <button
            type="button"
            onClick={fullscreen ? onToggleFocusMode : onOpenFullscreen}
            className="rounded-full border border-[#d7dbe3] bg-[#f8fafc] px-2.5 py-0.5 text-[10px] text-[#4b5563] transition hover:bg-[#eef2f7]"
            title={fullscreen ? "Toggle focus mode" : "Open fullscreen viewer"}
          >
            {fullscreen ? (isFocusMode ? "Focus on" : "Focus off") : "Fullscreen"}
          </button>
          <span className="inline-flex items-center gap-1 rounded-full border border-[#d7dbe3] bg-[#f8fafc] px-2 py-0.5 text-[#4b5563]">
            {streaming ? <span className="h-1.5 w-1.5 rounded-full bg-[#34c759]" /> : null}
            {streaming ? "Live" : "Replay"}
          </span>
        </div>
      </div>

      <p className="mb-2.5 text-[12px] font-medium text-[#1f2937]">
        {roleNarrative || desktopStatus}
      </p>

      <div className={`mx-auto ${viewerWidthClass}`}>
        <div
          className={`relative overflow-hidden rounded-2xl bg-[radial-gradient(circle_at_50%_-20%,rgba(121,152,201,0.2),transparent_44%),#0d1117] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.06)] ${viewerHeightClass}`}
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
              runId={runId}
              activeStepIndex={activeStepIndex}
              interactionSuggestion={interactionSuggestion}
              activeSceneData={activeSceneData}
              sceneDocumentUrl={sceneDocumentUrl}
              sceneSpreadsheetUrl={sceneSpreadsheetUrl}
              computerUseSessionId={computerUseSessionId}
              computerUseTask={computerUseTask}
              computerUseModel={computerUseModel}
              computerUseMaxIterations={computerUseMaxIterations}
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
            <div className="pointer-events-none absolute left-1/2 top-3 z-30 -translate-x-1/2 rounded-full border border-white/15 bg-[#111827] px-3 py-1 text-[10px] font-medium tracking-[0.045em] text-white/80">
              {sceneTransitionLabel}
            </div>
          ) : null}

          <DoneStageOverlay open={showDoneStage} title={doneStageTitle} detail={doneStageDetail} />

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
              <div className="rounded-xl border border-white/12 bg-[#111827] px-3 py-2">
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
      {!fullscreen &&
      (isBrowserScene || isEmailScene || isDocumentScene || isDocsScene || isSheetsScene) ? (
        <InteractionSuggestionsPanel suggestions={interactionSuggestion} />
      ) : null}
    </div>
  );
}

export { DesktopViewer };
