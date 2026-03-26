import type { ClickRippleEntry, HighlightRegion, ZoomHistoryEntry } from "../types";

const FRAME_VIEWPORT_BASE_WIDTH = 1366;
const FRAME_VIEWPORT_BASE_HEIGHT = 768;

const TRUSTED_LIVE_EMBED_HOSTS = new Set([
  "localhost",
  "127.0.0.1",
  "docs.google.com",
  "drive.google.com",
]);

function normalizeHost(value: string): string {
  try {
    return new URL(value).hostname.trim().toLowerCase();
  } catch {
    return "";
  }
}

function shouldPreferProxyForUrl(value: string): boolean {
  const normalized = String(value || "").trim();
  if (!normalized.startsWith("http://") && !normalized.startsWith("https://")) {
    return false;
  }
  if (normalized.toLowerCase().includes(".pdf")) {
    return false;
  }
  const host = normalizeHost(normalized);
  if (!host) {
    return true;
  }
  if (TRUSTED_LIVE_EMBED_HOSTS.has(host)) {
    return false;
  }
  if (host.endsWith(".localhost") || host.endsWith(".internal") || host.endsWith(".local")) {
    return false;
  }
  return true;
}

type BrowserCursorSource = "deterministic" | "suggested" | "synthetic_fallback" | "none";

type BrowserSceneProps = {
  activeDetail: string;
  activeEventType: string;
  activeTitle: string;
  action: string;
  actionPhase: string;
  actionStatus: string;
  actionTargetLabel: string;
  browserUrl: string;
  blockedSignal: boolean;
  canRenderLiveUrl: boolean;
  copyPulseText: string;
  copyPulseVisible: boolean;
  dedupedBrowserKeywords: string[];
  findMatchCount: number;
  findQuery: string;
  semanticFindResults: Array<{ term: string; confidence: number }>;
  onSnapshotError?: () => void;
  readingMode: boolean;
  sceneText: string;
  scrollDirection: string;
  scrollPercent: number | null;
  targetRegion: HighlightRegion | null;
  zoomHistory: ZoomHistoryEntry[];
  zoomLevel: number | null;
  zoomReason: string;
  compareLeft: string;
  compareRight: string;
  compareVerdict: string;
  verifierConflict: boolean;
  verifierConflictReason: string;
  verifierRecheckRequired: boolean;
  zoomEscalationRequested: boolean;
  showFindOverlay: boolean;
  snapshotUrl: string;
  renderQuality: string;
  pageIndex: number | null;
  openedPages: Array<{ url: string; title: string; pageIndex: number | null; reviewed: boolean }>;
  cursorX?: number | null;
  cursorY?: number | null;
  isClickEvent?: boolean;
  clickRipples?: ClickRippleEntry[];
  cursorSource?: BrowserCursorSource;
  narration?: string | null;
  roadmapSteps?: Array<{ toolId: string; title: string; whyThisStep: string }>;
  roadmapActiveIndex?: number;
  runId?: string;
  computerUseSessionId?: string;
  computerUseTask?: string;
  computerUseModel?: string;
  computerUseMaxIterations?: number | null;
  onComputerUseCancelled?: () => void;
};

export {
  FRAME_VIEWPORT_BASE_HEIGHT,
  FRAME_VIEWPORT_BASE_WIDTH,
  shouldPreferProxyForUrl,
};
export type { BrowserCursorSource, BrowserSceneProps };
