import {
  DiffViewer,
  DoneStageOverlay,
  InteractionSuggestionsPanel,
  TheatreDesktopViewer,
} from "@maia/theatre";
import { AgentDesktopScene } from "../AgentDesktopScene";
import type { InteractionSuggestion } from "./interactionSuggestionMerge";
import type { AgentActivityEvent } from "../../types";

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
  visibleEvents: AgentActivityEvent[];
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
  activeRoleLabel,
  roleNarrative,
  activeTitle,
  activeDetail,
  sceneText,
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
  visibleEvents,
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
  return (
    <TheatreDesktopViewer
      fullscreen={fullscreen}
      streaming={streaming}
      isTheaterView={isTheaterView}
      isFocusMode={isFocusMode}
      desktopStatus={desktopStatus}
      sceneTransitionLabel={sceneTransitionLabel}
      activeRoleLabel={activeRoleLabel}
      roleNarrative={roleNarrative}
      activeTitle={activeTitle}
      activeDetail={activeDetail}
      sceneText={sceneText}
      activeEventType={activeEventType}
      eventCursor={eventCursor}
      cursorPoint={cursorPoint}
      effectiveSnapshotUrl={effectiveSnapshotUrl}
      isBrowserScene={isBrowserScene}
      isEmailScene={isEmailScene}
      isDocumentScene={isDocumentScene}
      isDocsScene={isDocsScene}
      isSheetsScene={isSheetsScene}
      isSystemScene={isSystemScene}
      onToggleTheaterView={onToggleTheaterView}
      onToggleFocusMode={onToggleFocusMode}
      onOpenFullscreen={onOpenFullscreen}
      viewportOverlay={
        <>
          {activeEventType === "doc_insert_text" && activeSceneData["content_before"] ? (
            <DiffViewer
              before={String(activeSceneData["content_before"] || "")}
              after={String(activeSceneData["content_after"] || "")}
            />
          ) : null}
          <DoneStageOverlay open={showDoneStage} title={doneStageTitle} detail={doneStageDetail} />
        </>
      }
      footer={
        !fullscreen &&
        (isBrowserScene || isEmailScene || isDocumentScene || isDocsScene || isSheetsScene) ? (
          <InteractionSuggestionsPanel suggestions={interactionSuggestion} />
        ) : null
      }
      scene={
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
        visibleEvents={visibleEvents}
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
      }
    />
  );
}

export { DesktopViewer };
