import type { RefObject } from "react";

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
  activeSceneData: Record<string, unknown>;
  sceneDocumentUrl?: string;
  sceneSpreadsheetUrl?: string;
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

type BrowserFindState = {
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  showFindOverlay: boolean;
};

type SceneAnimationState = {
  copyPulseText: string;
  copyPulseVisible: boolean;
  docBodyScrollRef: RefObject<HTMLDivElement | null>;
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
  SceneAnimationState,
};
