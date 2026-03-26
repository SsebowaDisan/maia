import { DesktopSceneRouter, DefaultScene, parseApiSceneState } from "@maia/theatre";
import { renderRichText } from "../../utils/richText";
import { sanitizeComputerUseText } from "../../utils/userFacingComputerUse";
import { TeamChatSkin } from "./skins/TeamChatSkin";
import { asHttpUrl, compactValue, parseBrowserFindState, parseDocumentHighlights, parseHighlightRegions, parseLiveCopiedWords, parsePdfPlaybackState, parseZoomHistory, parseScrollPercent, parseSheetState } from "./helpers";
import { buildRoadmapSteps, buildTargetRegion, looksLikePdfUrl, parseOpenedPages, shouldRenderTeamChatScene } from "./sceneRuntime";
import { buildTeamChatMessages } from "./teamChatMessages";
import {
  ApiScene,
  BrowserScene,
  DocsScene,
  DocumentFallbackScene,
  DocumentPdfScene,
  EmailScene,
  SceneBoundary,
  SheetsScene,
  SnapshotScene,
  SystemScene,
} from "./lazyDesktopScenes";
import { useComputerUseBootstrap } from "./useComputerUseBootstrap";
import { useInteractionSceneState } from "./useInteractionSceneState";
import { useSceneAnimations } from "./useSceneAnimations";
import type { AgentDesktopSceneProps } from "./types";

function AgentDesktopScene({
  snapshotUrl,
  isBrowserScene,
  isEmailScene,
  isDocumentScene,
  isDocsScene,
  isSheetsScene,
  isSystemScene,
  canRenderPdfFrame,
  stageFileUrl,
  stageFileName,
  browserUrl,
  emailRecipient,
  emailSubject,
  emailBodyHint,
  docBodyHint,
  sheetBodyHint,
  sceneText,
  activeTitle,
  activeDetail,
  activeEventType,
  runId = "",
  activeStepIndex = null,
  visibleEvents = [],
  interactionSuggestion = null,
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  computerUseSessionId: computerUseSessionIdProp = "",
  computerUseTask: computerUseTaskProp = "",
  computerUseModel: computerUseModelProp = "",
  computerUseMaxIterations: computerUseMaxIterationsProp = null,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const highlightRegions = parseHighlightRegions(activeSceneData);
  const { dedupedBrowserKeywords, findMatchCount, findQuery, showFindOverlay, semanticFindResults } =
    parseBrowserFindState(activeSceneData, isBrowserScene, activeEventType, highlightRegions);
  const documentHighlights = parseDocumentHighlights(activeSceneData);

  const documentUrl = compactValue(sceneDocumentUrl) || compactValue(activeSceneData["document_url"]);
  const spreadsheetUrl = compactValue(sceneSpreadsheetUrl) || compactValue(activeSceneData["spreadsheet_url"]);
  const docsFrameUrl = asHttpUrl(documentUrl);
  const sheetsFrameUrl = asHttpUrl(spreadsheetUrl);
  const canRenderLiveUrl = Boolean(asHttpUrl(browserUrl));
  const runtimePdfUrl = [
    compactValue(activeSceneData["pdf_url"]),
    compactValue(activeSceneData["source_url"]),
    compactValue(activeSceneData["url"]),
    compactValue(activeSceneData["target_url"]),
    compactValue(activeSceneData["page_url"]),
    compactValue(activeSceneData["final_url"]),
    compactValue(activeSceneData["link"]),
    compactValue(sceneDocumentUrl),
    compactValue(browserUrl),
  ].find((candidate) => {
    if (!candidate) {
      return false;
    }
    return looksLikePdfUrl(candidate);
  }) || "";
  const effectivePdfUrl = asHttpUrl(stageFileUrl) || asHttpUrl(runtimePdfUrl);
  const blockedSignal = Boolean(activeSceneData["blocked_signal"]);
  const scrollDirection = compactValue(activeSceneData["scroll_direction"]).toLowerCase();
  const action = compactValue(activeSceneData["action"]).toLowerCase();
  const actionPhase = compactValue(activeSceneData["action_phase"]).toLowerCase();
  const actionStatus = compactValue(activeSceneData["action_status"]).toLowerCase();
  const actionTarget =
    activeSceneData["action_target"] && typeof activeSceneData["action_target"] === "object"
      ? (activeSceneData["action_target"] as Record<string, unknown>)
      : {};
  const actionMetadata =
    activeSceneData["action_metadata"] && typeof activeSceneData["action_metadata"] === "object"
      ? (activeSceneData["action_metadata"] as Record<string, unknown>)
      : {};
  const actionTargetLabel =
    compactValue(actionTarget["field_label"]) ||
    compactValue(actionTarget["field"]) ||
    compactValue(actionTarget["selector"]) ||
    compactValue(actionTarget["title"]) ||
    compactValue(actionTarget["url"]) ||
    compactValue(actionTarget["source_name"]);
  const compareMode =
    activeSceneData["compare_mode"] && typeof activeSceneData["compare_mode"] === "object"
      ? (activeSceneData["compare_mode"] as Record<string, unknown>)
      : {};
  const compareLeft =
    compactValue(activeSceneData["compare_left"]) ||
    compactValue(activeSceneData["compare_region_a"]) ||
    compactValue(activeSceneData["compare_a"]) ||
    compactValue(compareMode["left"]) ||
    compactValue(compareMode["region_a"]);
  const compareRight =
    compactValue(activeSceneData["compare_right"]) ||
    compactValue(activeSceneData["compare_region_b"]) ||
    compactValue(activeSceneData["compare_b"]) ||
    compactValue(compareMode["right"]) ||
    compactValue(compareMode["region_b"]);
  const compareVerdict = compactValue(activeSceneData["compare_verdict"]) || compactValue(compareMode["verdict"]);
  const {
    computerUseMaxIterations,
    computerUseModel,
    computerUseSessionId,
    computerUseTask,
    resetComputerUseFallback,
  } = useComputerUseBootstrap({
    activeDetail,
    activeEventType,
    activeSceneData,
    activeStepIndex,
    activeTitle,
    actionMetadata,
    actionTarget,
    browserUrl,
    computerUseMaxIterationsProp,
    computerUseModelProp,
    computerUseSessionIdProp,
    computerUseTaskProp,
    runId,
    sceneText,
  });
  const verifierConflict = Boolean(activeSceneData["verifier_conflict"]);
  const verifierConflictReason = compactValue(activeSceneData["verifier_conflict_reason"]);
  const verifierRecheckRequired = Boolean(activeSceneData["verifier_recheck_required"]);
  const zoomEscalationRequested = Boolean(activeSceneData["zoom_escalation_requested"]);
  const zoomRaw = Number(activeSceneData["zoom_level"] ?? actionTarget["zoom_level"]);
  const zoomLevel = Number.isFinite(zoomRaw) && zoomRaw > 0 ? zoomRaw : null;
  const zoomReason = compactValue(activeSceneData["zoom_reason"]) || compactValue(actionTarget["zoom_reason"]) || compactValue(activeSceneData["reason"]);
  const { regionSource, targetRegion } = buildTargetRegion(activeSceneData, actionTarget, actionTargetLabel);
  const readingMode = action === "scroll" || action === "extract" || showFindOverlay;
  const zoomHistory = parseZoomHistory(activeSceneData);
  const apiSceneState = parseApiSceneState({ activeSceneData, activeEventType, actionTargetLabel, actionStatus, sceneText, activeDetail });

  const { clipboardPreview, liveCopiedWordsKey } = parseLiveCopiedWords(activeSceneData);
  const scrollPercent = parseScrollPercent(activeSceneData["scroll_percent"]);
  const pageIndexRaw = Number(activeSceneData["page_index"]);
  const pageIndex = Number.isFinite(pageIndexRaw) && pageIndexRaw >= 1 ? Math.round(pageIndexRaw) : null;
  const renderQuality = compactValue(activeSceneData["render_quality"]).toLowerCase();
  const openedPages = parseOpenedPages(activeSceneData);
  const { pdfPage, pdfPageTotal, pdfScanRegion, pdfScrollDirection, pdfScrollPercent, pdfZoomLevel, pdfZoomReason, pdfTargetRegion, pdfCompareLeft, pdfCompareRight, pdfCompareVerdict, pdfFindQuery, pdfFindMatchCount, pdfSemanticFindResults, zoomHistory: pdfZoomHistory } = parsePdfPlaybackState(activeSceneData, activeEventType);
  const roadmapSteps = buildRoadmapSteps(activeSceneData);
  const roadmapActiveIdx = Number(activeSceneData["__roadmap_active_index"] ?? -1);
  const emailBodyPreview = String(emailBodyHint || "").trim();
  const rawDocBodyPreview = String(docBodyHint || "").trim();
  const rawSheetBodyPreview = String(sheetBodyHint || "").trim();

  const { copyPulseText, copyPulseVisible, emailBodyScrollRef, typedDocBodyPreview, typedSheetBodyPreview } = useSceneAnimations({
    activeEventType,
    clipboardPreview,
    emailBodyPreview,
    isDocsScene,
    isEmailScene,
    isSheetsScene,
    liveCopiedWordsKey,
    rawDocBodyPreview,
    rawSheetBodyPreview,
  });

  const emailBodyHtml = renderRichText(emailBodyPreview);
  const docBodyPreview = typedDocBodyPreview || rawDocBodyPreview;
  const docBodyHtml = renderRichText(docBodyPreview);
  const sheetBodyPreview = typedSheetBodyPreview || rawSheetBodyPreview;
  const { sheetPreviewRows, sheetStatusLine } = parseSheetState(sheetBodyPreview);
  const isPdfScene =
    (isDocumentScene || (isBrowserScene && Boolean(runtimePdfUrl))) &&
    (canRenderPdfFrame || Boolean(effectivePdfUrl)) &&
    !isSheetsScene &&
    !Boolean(docsFrameUrl) &&
    !Boolean(sheetsFrameUrl);

  const {
    actionForScene,
    actionTargetLabelForScene,
    clickRipples,
    cursorSource,
    cursorX,
    cursorY,
    isClickEvent,
    isDeterministicClickCue,
    scrollPercentForScene,
  } = useInteractionSceneState({
    action,
    actionTarget,
    actionTargetLabel,
    activeEventType,
    activeSceneData,
    activeStepIndex,
    interactionSuggestion,
    isBrowserScene,
    isDocsScene,
    isDocumentScene,
    isPdfScene,
    isSheetsScene,
    pdfScrollPercent,
    regionSource,
    runId,
    scrollPercent,
    targetRegion,
  });
  const interactionCursorProps = {
    cursorX,
    cursorY,
    isClickEvent: isDeterministicClickCue,
    clickRipples,
  };
  const displayActiveTitle = sanitizeComputerUseText(activeTitle);
  const displayActiveDetail = sanitizeComputerUseText(activeDetail);
  const displaySceneText = sanitizeComputerUseText(sceneText);
  const displayNarration = sanitizeComputerUseText(compactValue(activeSceneData["narration"]));

  const shouldRenderTeamChatSkin = shouldRenderTeamChatScene({
    activeEventType, activeSceneData, apiSceneActive: apiSceneState.isApiScene, isBrowserScene,
    isDocsScene, isDocumentScene, isEmailScene, isSheetsScene, isSystemScene, snapshotUrl,
  });
  const teamChatScene = shouldRenderTeamChatSkin ? (
    <TeamChatSkin
      messages={buildTeamChatMessages(visibleEvents, activeSceneData, activeDetail)}
      topic={String(activeSceneData?.topic || displayActiveTitle || "")}
      runId={runId || ""}
    />
  ) : null;

  return (
    <DesktopSceneRouter
      isBrowserScene={isBrowserScene}
      isPdfScene={isPdfScene}
      isEmailScene={isEmailScene}
      isDocumentScene={isDocumentScene}
      isDocsScene={isDocsScene}
      isSheetsScene={isSheetsScene}
      isSystemScene={isSystemScene}
      hasApiScene={apiSceneState.isApiScene}
      hasSnapshotScene={Boolean(snapshotUrl)}
      hasTeamChatScene={Boolean(teamChatScene)}
      browserScene={
        <SceneBoundary>
          <BrowserScene
            activeDetail={displayActiveDetail}
            activeEventType={activeEventType}
            activeTitle={displayActiveTitle}
            action={actionForScene}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabelForScene}
            browserUrl={browserUrl}
            blockedSignal={blockedSignal}
            canRenderLiveUrl={canRenderLiveUrl}
            copyPulseText={copyPulseText}
            copyPulseVisible={copyPulseVisible}
            dedupedBrowserKeywords={dedupedBrowserKeywords}
            findMatchCount={findMatchCount}
            findQuery={findQuery}
            semanticFindResults={semanticFindResults}
            onSnapshotError={onSnapshotError}
            readingMode={readingMode}
            sceneText={displaySceneText}
            scrollDirection={scrollDirection}
            scrollPercent={scrollPercentForScene}
            targetRegion={targetRegion}
            zoomHistory={zoomHistory}
            zoomLevel={zoomLevel}
            zoomReason={zoomReason}
            compareLeft={compareLeft}
            compareRight={compareRight}
            compareVerdict={compareVerdict}
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
            showFindOverlay={showFindOverlay}
            snapshotUrl={snapshotUrl}
            renderQuality={renderQuality}
            pageIndex={pageIndex}
            openedPages={openedPages}
            cursorX={cursorX}
            cursorY={cursorY}
            isClickEvent={isClickEvent}
            clickRipples={clickRipples}
            cursorSource={cursorSource}
            narration={displayNarration || null}
            roadmapSteps={roadmapSteps}
            roadmapActiveIndex={roadmapActiveIdx}
            runId={runId || undefined}
            computerUseSessionId={computerUseSessionId || undefined}
            computerUseTask={computerUseTask || undefined}
            computerUseModel={computerUseModel || undefined}
            computerUseMaxIterations={computerUseMaxIterations}
            onComputerUseCancelled={resetComputerUseFallback}
          />
        </SceneBoundary>
      }
      teamChatScene={teamChatScene}
      apiScene={<SceneBoundary><ApiScene activeTitle={displayActiveTitle} state={apiSceneState} /></SceneBoundary>}
      snapshotScene={
        <SceneBoundary>
          <SnapshotScene
            activeDetail={displayActiveDetail}
            activeTitle={displayActiveTitle}
            isBrowserScene={isBrowserScene}
            onSnapshotError={onSnapshotError}
            sceneText={displaySceneText}
            snapshotUrl={snapshotUrl}
          />
        </SceneBoundary>
      }
      emailScene={
        <SceneBoundary>
          <EmailScene
            activeEventType={activeEventType}
            activeDetail={displayActiveDetail}
            action={action}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabel}
            emailBodyPreview={emailBodyPreview}
            emailBodyHtml={emailBodyHtml}
            emailBodyScrollRef={emailBodyScrollRef}
            emailRecipient={emailRecipient}
            emailSubject={emailSubject}
          />
        </SceneBoundary>
      }
      sheetsScene={
        <SceneBoundary>
          <SheetsScene
            activeDetail={displayActiveDetail}
            activeEventType={activeEventType}
            action={actionForScene}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabelForScene}
            sceneText={displaySceneText}
            scrollDirection={scrollDirection}
            scrollPercent={scrollPercentForScene}
            sheetPreviewRows={sheetPreviewRows}
            sheetStatusLine={sheetStatusLine}
            sheetsFrameUrl={sheetsFrameUrl}
            zoomHistory={zoomHistory}
            compareLeft={compareLeft}
            compareRight={compareRight}
            compareVerdict={compareVerdict}
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
            {...interactionCursorProps}
          />
        </SceneBoundary>
      }
      pdfScene={
        <SceneBoundary>
          <DocumentPdfScene
            activeDetail={displayActiveDetail}
            activeEventType={activeEventType}
            action={actionForScene}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabelForScene}
            documentHighlights={documentHighlights}
            pdfPage={pdfPage}
            pdfPageTotal={pdfPageTotal}
            pdfScanRegion={pdfScanRegion}
            pdfScrollDirection={pdfScrollDirection}
            pdfScrollPercent={
              pdfScrollPercent ??
              (actionForScene === "scroll" ? scrollPercentForScene : null)
            }
            pdfZoomLevel={pdfZoomLevel}
            pdfZoomReason={pdfZoomReason}
            zoomHistory={pdfZoomHistory}
            pdfTargetRegion={pdfTargetRegion}
            pdfCompareLeft={pdfCompareLeft}
            pdfCompareRight={pdfCompareRight}
            pdfCompareVerdict={pdfCompareVerdict}
            pdfFindQuery={pdfFindQuery}
            pdfFindMatchCount={pdfFindMatchCount}
            pdfSemanticFindResults={pdfSemanticFindResults}
            verifierConflict={verifierConflict}
            verifierConflictReason={verifierConflictReason}
            verifierRecheckRequired={verifierRecheckRequired}
            zoomEscalationRequested={zoomEscalationRequested}
            sceneText={displaySceneText}
            stageFileUrl={effectivePdfUrl || stageFileUrl}
            {...interactionCursorProps}
          />
        </SceneBoundary>
      }
      docsScene={
        <SceneBoundary>
          <DocsScene
            activeDetail={displayActiveDetail}
            activeEventType={activeEventType}
            activeTitle={displayActiveTitle}
            action={actionForScene}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabelForScene}
            docBodyHtml={docBodyHtml}
            docBodyPreview={docBodyPreview}
            docsFrameUrl={docsFrameUrl}
            sceneText={displaySceneText}
            scrollDirection={scrollDirection}
            scrollPercent={scrollPercentForScene}
            {...interactionCursorProps}
          />
        </SceneBoundary>
      }
      documentScene={
        <SceneBoundary>
          <DocumentFallbackScene
            activeEventType={activeEventType}
            activeDetail={displayActiveDetail}
            action={actionForScene}
            actionPhase={actionPhase}
            actionStatus={actionStatus}
            actionTargetLabel={actionTargetLabelForScene}
            clipboardPreview={clipboardPreview}
            documentHighlights={documentHighlights}
            sceneText={displaySceneText}
            stageFileName={stageFileName}
            roadmapSteps={roadmapSteps}
            roadmapActiveIndex={roadmapActiveIdx}
          />
        </SceneBoundary>
      }
      systemScene={
        <SceneBoundary>
          <SystemScene
            activeEventType={activeEventType}
            activeDetail={displayActiveDetail}
            activeTitle={displayActiveTitle}
            sceneText={displaySceneText}
            activeSceneData={activeSceneData}
          />
        </SceneBoundary>
      }
      defaultScene={
        <DefaultScene isSystemScene={isSystemScene} stageFileName={stageFileName} />
      }
    />
  );
}

export { AgentDesktopScene };
