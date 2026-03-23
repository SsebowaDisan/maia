import type { RefObject } from "react";
import type { InteractionSuggestion } from "../agentActivityPanel/interactionSuggestionMerge";

type AgentDesktopSceneProps = {
  snapshotUrl: string;
  isBrowserScene: boolean;
  isEmailScene: boolean;
  isDocumentScene: boolean;
  isDocsScene: boolean;
  isSheetsScene: boolean;
  isSystemScene: boolean;
  canRenderPdfFrame: boolean;
  stageFileUrl: string;
  stageFileName: string;
  browserUrl: string;
  emailRecipient: string;
  emailSubject: string;
  emailBodyHint: string;
  docBodyHint: string;
  sheetBodyHint: string;
  sceneText: string;
  activeTitle: string;
  activeDetail: string;
  activeEventType: string;
  runId?: string;
  activeStepIndex?: number | null;
  visibleEvents?: import("../../types").AgentActivityEvent[];
  interactionSuggestion?: InteractionSuggestion[] | null;
  activeSceneData: Record<string, unknown>;
  sceneDocumentUrl?: string;
  sceneSpreadsheetUrl?: string;
  computerUseSessionId?: string;
  computerUseTask?: string;
  computerUseModel?: string;
  computerUseMaxIterations?: number | null;
  onSnapshotError?: () => void;
};

type HighlightColor = "yellow" | "green";

type HighlightRegion = {
  keyword: string;
  color: HighlightColor;
  x: number;
  y: number;
  width: number;
  height: number;
};

type DocumentHighlight = {
  word: string;
  snippet: string;
  color: HighlightColor;
};

type HighlightPalette = {
  border: string;
  fill: string;
  labelBackground: string;
  labelText: string;
};

type ZoomHistoryEntry = {
  eventRef: string;
  eventType: string;
  eventIndex: number | null;
  timestamp: string;
  action: "zoom_in" | "zoom_out" | "zoom_reset" | "zoom_to_region";
  sceneSurface: string;
  sceneRef: string;
  graphNodeId: string;
  zoomLevel: number | null;
  zoomReason: string;
  zoomPolicyTriggers: string[];
};

type BrowserFindState = {
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  showFindOverlay: boolean;
  semanticFindResults: Array<{ term: string; confidence: number }>;
};

type PdfPlaybackState = {
  pdfPage: number;
  pdfPageTotal: number;
  pdfScrollPercent: number | null;
  pdfScrollDirection: "up" | "down" | "";
  pdfScanRegion: string;
  pdfZoomLevel: number | null;
  pdfZoomReason: string;
  pdfTargetRegion: HighlightRegion | null;
  pdfCompareLeft: string;
  pdfCompareRight: string;
  pdfCompareVerdict: string;
  pdfFindQuery: string;
  pdfFindMatchCount: number;
  pdfSemanticFindResults: Array<{ term: string; confidence: number }>;
  zoomHistory: ZoomHistoryEntry[];
};

type SceneAnimationState = {
  copyPulseText: string;
  copyPulseVisible: boolean;
  emailBodyScrollRef: RefObject<HTMLDivElement | null>;
  typedDocBodyPreview: string;
  typedSheetBodyPreview: string;
};

export type {
  AgentDesktopSceneProps,
  BrowserFindState,
  DocumentHighlight,
  HighlightColor,
  HighlightPalette,
  HighlightRegion,
  PdfPlaybackState,
  SceneAnimationState,
  ZoomHistoryEntry,
};
