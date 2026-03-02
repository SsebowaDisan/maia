import { renderRichText } from "../../utils/richText";
import { BrowserScene } from "./BrowserScene";
import { DocsScene } from "./DocsScene";
import { DocumentFallbackScene, DocumentPdfScene } from "./DocumentScenes";
import { EmailScene } from "./EmailScene";
import {
  asHttpUrl,
  compactValue,
  parseBrowserFindState,
  parseDocumentHighlights,
  parseHighlightRegions,
  parseLiveCopiedWords,
  parseScrollPercent,
  parseSheetState,
} from "./helpers";
import { SheetsScene } from "./SheetsScene";
import { SnapshotScene } from "./SnapshotScene";
import { DefaultScene, SystemScene } from "./SystemFallbackScenes";
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
  activeSceneData,
  sceneDocumentUrl,
  sceneSpreadsheetUrl,
  onSnapshotError,
}: AgentDesktopSceneProps) {
  const highlightRegions = parseHighlightRegions(activeSceneData);
  const { dedupedBrowserKeywords, findMatchCount, findQuery, showFindOverlay } =
    parseBrowserFindState(activeSceneData, isBrowserScene, activeEventType, highlightRegions);
  const documentHighlights = parseDocumentHighlights(activeSceneData);

  const documentUrl =
    compactValue(sceneDocumentUrl) || compactValue(activeSceneData["document_url"]);
  const spreadsheetUrl =
    compactValue(sceneSpreadsheetUrl) || compactValue(activeSceneData["spreadsheet_url"]);
  const docsFrameUrl = asHttpUrl(documentUrl);
  const sheetsFrameUrl = asHttpUrl(spreadsheetUrl);
  const canRenderLiveUrl = Boolean(asHttpUrl(browserUrl));
  const providerLabel = compactValue(activeSceneData["provider"]) || compactValue(activeSceneData["web_provider"]);
  const renderQualityLabel = compactValue(activeSceneData["render_quality"]);
  const blockedSignal = Boolean(activeSceneData["blocked_signal"]);
  const densityRaw = Number(activeSceneData["content_density"]);
  const contentDensityLabel = Number.isFinite(densityRaw) ? densityRaw.toFixed(2) : "";

  const { clipboardPreview, liveCopiedWordsKey } = parseLiveCopiedWords(activeSceneData);
  const scrollPercent = parseScrollPercent(activeSceneData["scroll_percent"]);
  const emailBodyPreview = String(emailBodyHint || "").trim() || "Composing message body...";
  const rawDocBodyPreview = String(docBodyHint || "").trim();
  const rawSheetBodyPreview = String(sheetBodyHint || "").trim();

  const {
    copyPulseText,
    copyPulseVisible,
    docBodyScrollRef,
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

  if (isBrowserScene) {
    return (
      <BrowserScene
        activeDetail={activeDetail}
        activeTitle={activeTitle}
        browserUrl={browserUrl}
        blockedSignal={blockedSignal}
        canRenderLiveUrl={canRenderLiveUrl}
        copyPulseText={copyPulseText}
        copyPulseVisible={copyPulseVisible}
        dedupedBrowserKeywords={dedupedBrowserKeywords}
        findMatchCount={findMatchCount}
        findQuery={findQuery}
        highlightRegions={highlightRegions}
        onSnapshotError={onSnapshotError}
        providerLabel={providerLabel}
        renderQualityLabel={renderQualityLabel}
        contentDensityLabel={contentDensityLabel}
        sceneText={sceneText}
        scrollPercent={scrollPercent}
        showFindOverlay={showFindOverlay}
        snapshotUrl={snapshotUrl}
      />
    );
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
        sceneText={sceneText}
        sheetPreviewRows={sheetPreviewRows}
        sheetStatusLine={sheetStatusLine}
        sheetsFrameUrl={sheetsFrameUrl}
      />
    );
  }

  if (isDocsScene) {
    return (
      <DocsScene
        activeDetail={activeDetail}
        activeTitle={activeTitle}
        docBodyHtml={docBodyHtml}
        docBodyPreview={docBodyPreview}
        docBodyScrollRef={docBodyScrollRef}
        docsFrameUrl={docsFrameUrl}
        sceneText={sceneText}
      />
    );
  }

  if (isDocumentScene && canRenderPdfFrame) {
    return <DocumentPdfScene documentHighlights={documentHighlights} stageFileUrl={stageFileUrl} />;
  }

  if (isDocumentScene) {
    return (
      <DocumentFallbackScene
        activeDetail={activeDetail}
        clipboardPreview={clipboardPreview}
        documentHighlights={documentHighlights}
        sceneText={sceneText}
        stageFileName={stageFileName}
      />
    );
  }

  if (isSystemScene) {
    return <SystemScene activeDetail={activeDetail} activeTitle={activeTitle} sceneText={sceneText} />;
  }

  return <DefaultScene isSystemScene={isSystemScene} stageFileName={stageFileName} />;
}

export { AgentDesktopScene };
