import { useEffect, useRef, useState } from "react";
import { renderRichText } from "../../utils/richText";
import { ApiScene } from "./ApiScene";
import { BrowserScene } from "./BrowserScene";
import type { ClickRippleEntry } from "./ClickRipple";
import { DocsScene } from "./DocsScene";
import { DocumentFallbackScene, DocumentPdfScene } from "./DocumentScenes";
import { EmailScene } from "./EmailScene";
import { parseApiSceneState } from "./api_scene_state";
import {
  asHttpUrl,
  compactValue,
  parseBrowserFindState,
  parseDocumentHighlights,
  parseHighlightRegions,
  parseLiveCopiedWords,
  parsePdfPlaybackState,
  parseZoomHistory,
  parseScrollPercent,
  parseSheetState,
} from "./helpers";
import { SheetsScene } from "./SheetsScene";
import { SnapshotScene } from "./SnapshotScene";
import { DefaultScene, SystemScene } from "./SystemFallbackScenes";
import { useSceneAnimations } from "./useSceneAnimations";
import type { AgentDesktopSceneProps } from "./types";

function looksLikePdfUrl(value: string): boolean {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) {
    return false;
  }
  return (
    normalized.includes(".pdf") ||
    normalized.includes("application/pdf") ||
    normalized.includes("/pdf?")
  );
}

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
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const highlightRegions = parseHighlightRegions(activeSceneData);
  const { dedupedBrowserKeywords, findMatchCount, findQuery, showFindOverlay, semanticFindResults } =
    parseBrowserFindState(activeSceneData, isBrowserScene, activeEventType, highlightRegions);
  const documentHighlights = parseDocumentHighlights(activeSceneData);

  const documentUrl =
    compactValue(sceneDocumentUrl) || compactValue(activeSceneData["document_url"]);
  const spreadsheetUrl =
    compactValue(sceneSpreadsheetUrl) || compactValue(activeSceneData["spreadsheet_url"]);
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
  const compareVerdict =
    compactValue(activeSceneData["compare_verdict"]) || compactValue(compareMode["verdict"]);
  const verifierConflict = Boolean(activeSceneData["verifier_conflict"]);
  const verifierConflictReason = compactValue(activeSceneData["verifier_conflict_reason"]);
  const verifierRecheckRequired = Boolean(activeSceneData["verifier_recheck_required"]);
  const zoomEscalationRequested = Boolean(activeSceneData["zoom_escalation_requested"]);
  const zoomRaw = Number(activeSceneData["zoom_level"] ?? actionTarget["zoom_level"]);
  const zoomLevel = Number.isFinite(zoomRaw) && zoomRaw > 0 ? zoomRaw : null;
  const zoomReason =
    compactValue(activeSceneData["zoom_reason"]) ||
    compactValue(actionTarget["zoom_reason"]) ||
    compactValue(activeSceneData["reason"]);
  const regionSource =
    activeSceneData["target_region"] && typeof activeSceneData["target_region"] === "object"
      ? (activeSceneData["target_region"] as Record<string, unknown>)
      : actionTarget;
  const parsePercent = (value: unknown): number | null => {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    return Math.max(0, Math.min(100, parsed));
  };
  const regionX = parsePercent(regionSource["x"] ?? regionSource["region_x"]);
  const regionY = parsePercent(regionSource["y"] ?? regionSource["region_y"]);
  const regionWidth = parsePercent(regionSource["width"] ?? regionSource["region_width"]);
  const regionHeight = parsePercent(regionSource["height"] ?? regionSource["region_height"]);
  const targetRegion =
    regionX !== null &&
    regionY !== null &&
    regionWidth !== null &&
    regionHeight !== null &&
    regionWidth > 0 &&
    regionHeight > 0
      ? {
          keyword: actionTargetLabel || "target",
          color: "yellow" as const,
          x: regionX,
          y: regionY,
          width: regionWidth,
          height: regionHeight,
        }
      : null;
  const readingMode = action === "scroll" || action === "extract" || showFindOverlay;
  const zoomHistory = parseZoomHistory(activeSceneData);
  const apiSceneState = parseApiSceneState({
    activeSceneData,
    activeEventType,
    actionTargetLabel,
    actionStatus,
    sceneText,
    activeDetail,
  });

  const { clipboardPreview, liveCopiedWordsKey } = parseLiveCopiedWords(activeSceneData);
  const scrollPercent = parseScrollPercent(activeSceneData["scroll_percent"]);
  const pageIndexRaw = Number(activeSceneData["page_index"]);
  const pageIndex = Number.isFinite(pageIndexRaw) && pageIndexRaw >= 1 ? Math.round(pageIndexRaw) : null;
  const renderQuality = compactValue(activeSceneData["render_quality"]).toLowerCase();
  const openedPages = Array.isArray(activeSceneData["opened_pages"])
    ? activeSceneData["opened_pages"]
        .map((row) => {
          if (!row || typeof row !== "object") return null;
          const item = row as Record<string, unknown>;
          const url = compactValue(item["url"]);
          if (!url || (!url.startsWith("http://") && !url.startsWith("https://"))) return null;
          const title = compactValue(item["title"]);
          const pageIdx = Number(item["page_index"]);
          const reviewed = Boolean(item["reviewed"]);
          return {
            url,
            title,
            pageIndex: Number.isFinite(pageIdx) && pageIdx >= 1 ? Math.round(pageIdx) : null,
            reviewed,
          };
        })
        .filter((row): row is { url: string; title: string; pageIndex: number | null; reviewed: boolean } => Boolean(row))
        .slice(-24)
    : [];
  const {
    pdfPage,
    pdfPageTotal,
    pdfScanRegion,
    pdfScrollDirection,
    pdfScrollPercent,
    pdfZoomLevel,
    pdfZoomReason,
    pdfTargetRegion,
    pdfCompareLeft,
    pdfCompareRight,
    pdfCompareVerdict,
    pdfFindQuery,
    pdfFindMatchCount,
    pdfSemanticFindResults,
    zoomHistory: pdfZoomHistory,
  } = parsePdfPlaybackState(activeSceneData, activeEventType);
  const roadmapSteps = Array.isArray(activeSceneData["__roadmap_steps"])
    ? (activeSceneData["__roadmap_steps"] as Array<{ toolId: string; title: string; whyThisStep: string }>)
    : [];
  const roadmapActiveIdx = Number(activeSceneData["__roadmap_active_index"] ?? -1);
  const emailBodyPreview = String(emailBodyHint || "").trim();
  const rawDocBodyPreview = String(docBodyHint || "").trim();
  const rawSheetBodyPreview = String(sheetBodyHint || "").trim();

  const {
    copyPulseText,
    copyPulseVisible,
    emailBodyScrollRef,
    typedDocBodyPreview,
    typedSheetBodyPreview,
  } = useSceneAnimations({
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

  // T1: Ghost Cursor + Click Ripple + Interaction Trace
  const cursorX = parsePercent(activeSceneData["cursor_x"]);
  const cursorY = parsePercent(activeSceneData["cursor_y"]);
  const isClickEvent = /browser_(left_|right_|double_)?click/i.test(activeEventType);
  const rippleCounterRef = useRef(0);
  const prevEventTypeRef = useRef<string>("");
  const [clickRipples, setClickRipples] = useState<ClickRippleEntry[]>([]);

  useEffect(() => {
    if (activeEventType === prevEventTypeRef.current) return;
    prevEventTypeRef.current = activeEventType;
    if (!isClickEvent || cursorX === null || cursorY === null) return;
    const id = String(++rippleCounterRef.current);
    setClickRipples((prev) => [...prev, { id, x: cursorX, y: cursorY, type: "click" as const }]);
    const timer = setTimeout(() => {
      setClickRipples((prev) => prev.filter((r) => r.id !== id));
    }, 700);
    return () => clearTimeout(timer);
  }, [activeEventType, isClickEvent, cursorX, cursorY]);

  if (isBrowserScene && !isPdfScene) {
    return (
      <BrowserScene
        activeDetail={activeDetail}
        activeEventType={activeEventType}
        activeTitle={activeTitle}
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
        browserUrl={browserUrl}
        blockedSignal={blockedSignal}
        canRenderLiveUrl={canRenderLiveUrl}
        copyPulseText={copyPulseText}
        copyPulseVisible={copyPulseVisible}
        dedupedBrowserKeywords={dedupedBrowserKeywords}
        findMatchCount={findMatchCount}
        findQuery={findQuery}
        semanticFindResults={semanticFindResults}
        highlightRegions={highlightRegions}
        onSnapshotError={onSnapshotError}
        readingMode={readingMode}
        sceneText={sceneText}
        scrollDirection={scrollDirection}
        scrollPercent={scrollPercent}
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
        narration={compactValue(activeSceneData["narration"]) || null}
        roadmapSteps={roadmapSteps}
        roadmapActiveIndex={roadmapActiveIdx}
      />
    );
  }

  if (apiSceneState.isApiScene && !isBrowserScene && !isDocumentScene && !isDocsScene && !isSheetsScene) {
    return <ApiScene activeTitle={activeTitle} state={apiSceneState} />;
  }

  if (
    snapshotUrl &&
    !isEmailScene &&
    !isDocumentScene &&
    !isDocsScene &&
    !isSheetsScene &&
    !isSystemScene
  ) {
    return (
      <SnapshotScene
        activeDetail={activeDetail}
        activeTitle={activeTitle}
        isBrowserScene={isBrowserScene}
        onSnapshotError={onSnapshotError}
        sceneText={sceneText}
        snapshotUrl={snapshotUrl}
      />
    );
  }

  if (isEmailScene) {
    return (
      <EmailScene
        activeEventType={activeEventType}
        activeDetail={activeDetail}
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
    );
  }

  if (isSheetsScene) {
    return (
      <SheetsScene
        activeDetail={activeDetail}
        activeEventType={activeEventType}
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
        sceneText={sceneText}
        scrollDirection={scrollDirection}
        scrollPercent={scrollPercent}
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
      />
    );
  }

  if (isPdfScene) {
    return (
      <DocumentPdfScene
        activeDetail={activeDetail}
        activeEventType={activeEventType}
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
        documentHighlights={documentHighlights}
        pdfPage={pdfPage}
        pdfPageTotal={pdfPageTotal}
        pdfScanRegion={pdfScanRegion}
        pdfScrollDirection={pdfScrollDirection}
        pdfScrollPercent={pdfScrollPercent}
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
        sceneText={sceneText}
        stageFileUrl={effectivePdfUrl || stageFileUrl}
      />
    );
  }

  if (isDocsScene) {
    return (
      <DocsScene
        activeDetail={activeDetail}
        activeEventType={activeEventType}
        activeTitle={activeTitle}
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
        docBodyHtml={docBodyHtml}
        docBodyPreview={docBodyPreview}
        docsFrameUrl={docsFrameUrl}
        sceneText={sceneText}
        scrollDirection={scrollDirection}
        scrollPercent={scrollPercent}
      />
    );
  }

  if (isDocumentScene) {
    return (
      <DocumentFallbackScene
        activeEventType={activeEventType}
        activeDetail={activeDetail}
        action={action}
        actionPhase={actionPhase}
        actionStatus={actionStatus}
        actionTargetLabel={actionTargetLabel}
        clipboardPreview={clipboardPreview}
        documentHighlights={documentHighlights}
        sceneText={sceneText}
        stageFileName={stageFileName}
        roadmapSteps={roadmapSteps}
        roadmapActiveIndex={roadmapActiveIdx}
      />
    );
  }

  if (isSystemScene) {
    return (
      <SystemScene
        activeEventType={activeEventType}
        activeDetail={activeDetail}
        activeTitle={activeTitle}
        sceneText={sceneText}
      />
    );
  }

  return <DefaultScene isSystemScene={isSystemScene} stageFileName={stageFileName} />;
}

export { AgentDesktopScene };
