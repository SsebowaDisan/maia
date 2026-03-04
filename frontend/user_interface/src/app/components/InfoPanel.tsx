import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { toast } from "sonner";

import { buildRawFileUrl } from "../../api/client";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import type { AgentSourceRecord, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import { CitationPdfPreview } from "./CitationPdfPreview";
import { MindmapViewer } from "./MindmapViewer";
import { getMindmapPayload } from "./infoPanelDerived";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  userPrompt?: string;
  assistantHtml?: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  sourcesUsed?: AgentSourceRecord[];
  webSummary?: Record<string, unknown>;
  sourceUsage?: SourceUsageRecord[];
  indexId?: number | null;
  onClearCitationFocus?: () => void;
  onSelectCitationFocus?: (citation: CitationFocus) => void;
  onAskMindmapNode?: (payload: {
    nodeId: string;
    title: string;
    text: string;
    pageRef?: string;
    sourceId?: string;
    sourceName?: string;
  }) => void;
  width?: number;
}

type ViewerHeightKey = "mindmap" | "website" | "citation";

type ViewerHeights = {
  mindmap: number;
  website: number;
  citation: number;
};

const VIEWER_HEIGHT_STORAGE_KEY = "maia.info-panel.viewer-heights.v1";
const DEFAULT_VIEWER_HEIGHTS: ViewerHeights = {
  mindmap: 520,
  website: 280,
  citation: 420,
};
const VIEWER_HEIGHT_LIMITS: Record<ViewerHeightKey, { min: number; max: number }> = {
  mindmap: { min: 260, max: 1000 },
  website: { min: 180, max: 900 },
  citation: { min: 220, max: 1000 },
};

function clampViewerHeight(viewer: ViewerHeightKey, rawValue: unknown): number {
  const limits = VIEWER_HEIGHT_LIMITS[viewer];
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    return DEFAULT_VIEWER_HEIGHTS[viewer];
  }
  return Math.max(limits.min, Math.min(limits.max, Math.round(parsed)));
}

function loadViewerHeights(): ViewerHeights {
  if (typeof window === "undefined") {
    return { ...DEFAULT_VIEWER_HEIGHTS };
  }
  try {
    const parsed = JSON.parse(window.localStorage.getItem(VIEWER_HEIGHT_STORAGE_KEY) || "{}") as
      | Partial<ViewerHeights>
      | null;
    return {
      mindmap: clampViewerHeight("mindmap", parsed?.mindmap),
      website: clampViewerHeight("website", parsed?.website),
      citation: clampViewerHeight("citation", parsed?.citation),
    };
  } catch {
    return { ...DEFAULT_VIEWER_HEIGHTS };
  }
}

export function InfoPanel({
  citationFocus = null,
  selectedConversationId = null,
  userPrompt = "",
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  sourcesUsed = [],
  webSummary = {},
  indexId = null,
  onClearCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const [viewerHeights, setViewerHeights] = useState<ViewerHeights>(() => loadViewerHeights());
  const dragViewerRef = useRef<ViewerHeightKey | null>(null);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);
  const dragCleanupRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem(VIEWER_HEIGHT_STORAGE_KEY, JSON.stringify(viewerHeights));
  }, [viewerHeights]);

  const setViewerHeight = (viewer: ViewerHeightKey, value: unknown) => {
    setViewerHeights((previous) => {
      const nextValue = clampViewerHeight(viewer, value);
      if (previous[viewer] === nextValue) {
        return previous;
      }
      return { ...previous, [viewer]: nextValue };
    });
  };

  const beginViewerResize = (viewer: ViewerHeightKey, event: ReactMouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (dragCleanupRef.current) {
      dragCleanupRef.current();
      dragCleanupRef.current = null;
    }
    dragViewerRef.current = viewer;
    dragStartYRef.current = event.clientY;
    dragStartHeightRef.current = viewerHeights[viewer];

    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";

    const onMove = (moveEvent: MouseEvent) => {
      const activeViewer = dragViewerRef.current;
      if (!activeViewer) {
        return;
      }
      if ((moveEvent.buttons & 1) !== 1) {
        onStop();
        return;
      }
      const deltaY = moveEvent.clientY - dragStartYRef.current;
      setViewerHeight(activeViewer, dragStartHeightRef.current + deltaY);
    };

    const onStop = () => {
      dragViewerRef.current = null;
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onStop);
      window.removeEventListener("mouseleave", onStop);
      window.removeEventListener("blur", onStop);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (dragCleanupRef.current === onStop) {
        dragCleanupRef.current = null;
      }
    };
    const onVisibilityChange = () => {
      if (document.visibilityState !== "visible") {
        onStop();
      }
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onStop);
    window.addEventListener("mouseleave", onStop);
    window.addEventListener("blur", onStop);
    document.addEventListener("visibilitychange", onVisibilityChange);
    dragCleanupRef.current = onStop;
  };

  useEffect(() => {
    return () => {
      if (dragCleanupRef.current) {
        dragCleanupRef.current();
        dragCleanupRef.current = null;
      }
    };
  }, []);

  const renderViewerResizeHandle = (viewer: ViewerHeightKey, label: string) => {
    return (
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label={`Resize ${label} viewer`}
        onMouseDown={(mouseEvent) => beginViewerResize(viewer, mouseEvent)}
        className="group relative mt-2 h-3 cursor-row-resize select-none"
      >
        <div className="absolute left-1/2 top-1/2 h-[2px] w-16 -translate-x-1/2 -translate-y-1/2 rounded-full bg-black/15 transition-colors group-hover:bg-[#2f2f34]/60" />
      </div>
    );
  };

  const normalizeHttpUrl = (rawValue: unknown): string => {
    const value = String(rawValue || "").split(/\s+/).join(" ").trim();
    if (!value) {
      return "";
    }
    try {
      const parsed = new URL(value);
      if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
        return "";
      }
      return parsed.toString();
    } catch {
      return "";
    }
  };

  const normalizeUrlToken = (rawValue: unknown): string => {
    const value = String(rawValue || "")
      .trim()
      .replace(/^[("'`<\[]+/, "")
      .replace(/[>"'`)\],.;:!?]+$/, "");
    return normalizeHttpUrl(value);
  };

  const artifactUrlPathSegments = new Set([
    "extract",
    "source",
    "link",
    "evidence",
    "citation",
    "title",
    "markdown",
    "content",
    "published",
    "time",
    "url",
  ]);

  const isLikelyLabelArtifactUrl = (rawValue: unknown): boolean => {
    const candidate = normalizeHttpUrl(rawValue);
    if (!candidate) {
      return false;
    }
    try {
      const parsed = new URL(candidate);
      const segments = String(parsed.pathname || "")
        .split("/")
        .filter(Boolean)
        .map((segment) => segment.trim().toLowerCase());
      if (segments.length !== 1) {
        return false;
      }
      const token = segments[0].replace(/[:]+$/, "");
      return artifactUrlPathSegments.has(token);
    } catch {
      return false;
    }
  };

  const extractExplicitSourceUrl = (rawText: unknown): string => {
    const text = String(rawText || "");
    const patterns = [
      /\bURL\s*Source\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
      /\bsource_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
      /\bpage_url\s*[:=]\s*(https?:\/\/[^\s<>'")\]]+)/i,
      /\bsource\s*url\s*:\s*(https?:\/\/[^\s<>'")\]]+)/i,
    ];
    for (const pattern of patterns) {
      const match = text.match(pattern);
      const candidate = normalizeUrlToken(match?.[1] || "");
      if (candidate) {
        return candidate;
      }
    }
    return "";
  };

  const choosePreferredSourceUrl = (candidates: Array<string | null | undefined>): string => {
    for (const rawCandidate of candidates) {
      const normalized = normalizeHttpUrl(rawCandidate);
      if (!normalized) {
        continue;
      }
      if (isLikelyLabelArtifactUrl(normalized)) {
        continue;
      }
      return normalized;
    }
    return "";
  };

  const normalizeWebsiteHighlightText = (rawValue: unknown): string => {
    let text = String(rawValue || "").replace(/\s+/g, " ").trim();
    if (!text) {
      return "";
    }
    text = text.replace(/\bURL\s*Source\s*:\s*https?:\/\/[^\s<>'")\]]+/gi, " ");
    text = text.replace(/\bPublished\s*Time\s*:\s*[^]+?(?=\bMarkdown\s*Content\s*:|$)/i, " ");
    text = text.replace(/\bMarkdown\s*Content\s*:\s*/i, " ");
    text = text.replace(/https?:\/\/[^\s<>'")\]]+/gi, " ");
    text = text.replace(/\[[^\]]+\]\([^)]+\)/g, " ");
    text = text.replace(/[*#=|_]{2,}/g, " ");
    text = text.replace(/\s+/g, " ").trim();
    if (text.length <= 160) {
      return text;
    }
    const clipped = text.slice(0, 160);
    const sentenceCut = Math.max(clipped.lastIndexOf("."), clipped.lastIndexOf("!"), clipped.lastIndexOf("?"));
    if (sentenceCut >= 40) {
      return clipped.slice(0, sentenceCut + 1).trim();
    }
    const wordCut = clipped.lastIndexOf(" ");
    if (wordCut >= 40) {
      return clipped.slice(0, wordCut).trim();
    }
    return clipped.trim();
  };

  const resolveWebsiteHighlightText = (focus: CitationFocus | null | undefined): string => {
    const titleMatch = String(focus?.extract || "").match(
      /\bTitle\s*:\s*([^|]+?)(?=\s+URL\s*Source\s*:|\s+Published\s*Time\s*:|\s+Markdown\s*Content\s*:|$)/i,
    );
    const fromTitle = normalizeWebsiteHighlightText(titleMatch?.[1] || "");
    if (fromTitle.length >= 8) {
      return fromTitle;
    }
    const fromExtract = normalizeWebsiteHighlightText(focus?.extract || "");
    if (fromExtract.length >= 8) {
      return fromExtract;
    }
    const fromClaim = normalizeWebsiteHighlightText(focus?.claimText || "");
    if (fromClaim.length >= 8) {
      return fromClaim;
    }
    return "";
  };

  const buildWebsitePreviewUrl = (params: {
    url: string;
    highlightText?: string;
    claimText?: string;
    questionText?: string;
  }): string => {
    const normalizedUrl = normalizeHttpUrl(params.url);
    if (!normalizedUrl) {
      return "";
    }
    const query = new URLSearchParams();
    query.set("url", normalizedUrl);
    const highlight = normalizeWebsiteHighlightText(params.highlightText || "").slice(0, 220);
    if (highlight.length >= 8) {
      query.set("highlight", highlight);
    }
    const claim = normalizeWebsiteHighlightText(params.claimText || "").slice(0, 220);
    if (claim.length >= 8) {
      query.set("claim", claim);
    }
    const question = normalizeWebsiteHighlightText(params.questionText || "").slice(0, 260);
    if (question.length >= 6) {
      query.set("question", question);
    }
    return `/api/web/preview?${query.toString()}`;
  };

  const evidenceCards = useMemo(() => parseEvidence(String(infoHtml || "")), [infoHtml]);

  const citationWebsiteUrl = useMemo(() => {
    const direct = normalizeHttpUrl(citationFocus?.sourceUrl);
    const fromExtract = extractExplicitSourceUrl(citationFocus?.extract || "");
    const sourceNameUrl = normalizeHttpUrl(citationFocus?.sourceName);
    const rankedDirect = choosePreferredSourceUrl([fromExtract, direct, sourceNameUrl]);
    const evidenceId = String(citationFocus?.evidenceId || "").toLowerCase();
    if (evidenceId) {
      const matchedById = evidenceCards.find((card) => String(card.id || "").toLowerCase() === evidenceId);
      const matchedByIdUrl = choosePreferredSourceUrl([
        extractExplicitSourceUrl(matchedById?.extract || ""),
        normalizeHttpUrl(matchedById?.sourceUrl),
      ]);
      if (matchedByIdUrl) {
        return choosePreferredSourceUrl([matchedByIdUrl, rankedDirect]);
      }
    }
    const focusExtract = String(citationFocus?.extract || "").toLowerCase();
    if (focusExtract) {
      const matchedByText = evidenceCards.find(
        (card) =>
          String(card.extract || "").toLowerCase().includes(focusExtract.slice(0, 96)) ||
          focusExtract.includes(String(card.extract || "").toLowerCase().slice(0, 96)),
      );
      const matchedByTextUrl = choosePreferredSourceUrl([
        extractExplicitSourceUrl(matchedByText?.extract || ""),
        normalizeHttpUrl(matchedByText?.sourceUrl),
      ]);
      if (matchedByTextUrl) {
        return choosePreferredSourceUrl([matchedByTextUrl, rankedDirect]);
      }
    }
    return rankedDirect || "";
  }, [citationFocus, evidenceCards]);

  const websitePreviewUrl = useMemo(() => {
    const ranked: Array<{ url: string; score: number }> = [];
    const seen = new Set<string>();
    const addCandidate = (rawValue: unknown, score: number) => {
      const normalized = normalizeHttpUrl(rawValue);
      if (!normalized || seen.has(normalized)) {
        return;
      }
      seen.add(normalized);
      ranked.push({ url: normalized, score });
    };

    for (const source of sourcesUsed) {
      if (!source || typeof source !== "object") {
        continue;
      }
      const sourceType = String(source.source_type || "").toLowerCase();
      const url = String(source.url || "").trim();
      if (!url) {
        continue;
      }
      const webTypeScore = /(^|_)(website|web|web_source|url)(_|$)/.test(sourceType) ? 300 : 180;
      addCandidate(url, webTypeScore);
    }

    const topSources = (
      (webSummary as { evidence?: { top_sources?: Array<{ url?: unknown }> } }).evidence?.top_sources || []
    ) as Array<{ url?: unknown }>;
    for (const row of topSources) {
      addCandidate(row?.url, 240);
    }

    const evidenceItems = (
      (webSummary as { evidence?: { items?: Array<{ url?: unknown; evidence?: Array<{ url?: unknown }> }> } })
        .evidence?.items || []
    ) as Array<{ url?: unknown; evidence?: Array<{ url?: unknown }> }>;
    for (const item of evidenceItems) {
      addCandidate(item?.url, 220);
      const nestedEvidence = Array.isArray(item?.evidence) ? item.evidence : [];
      for (const evidenceRow of nestedEvidence) {
        addCandidate(evidenceRow?.url, 210);
      }
    }

    const hrefMatches = String(infoHtml || "").match(/href=['"]([^'"]+)['"]/gi) || [];
    for (const rawMatch of hrefMatches) {
      const match = rawMatch.match(/href=['"]([^'"]+)['"]/i);
      addCandidate(match?.[1], 120);
    }

    const promptUrlMatches = String(userPrompt || "").match(/https?:\/\/[^\s<>'")\]]+/gi) || [];
    for (const rawUrl of promptUrlMatches) {
      addCandidate(String(rawUrl || "").replace(/[.,;:!?]+$/, ""), 260);
    }

    if (!ranked.length) {
      return "";
    }
    ranked.sort((left, right) => right.score - left.score || left.url.localeCompare(right.url));
    return ranked[0]?.url || "";
  }, [infoHtml, sourcesUsed, userPrompt, webSummary]);

  const activeWebsiteUrl = citationWebsiteUrl || websitePreviewUrl;
  const websiteHighlightText = resolveWebsiteHighlightText(citationFocus);
  const activeWebsiteFrameUrl = useMemo(() => {
    if (!activeWebsiteUrl) {
      return "";
    }
    return buildWebsitePreviewUrl({
      url: activeWebsiteUrl,
      highlightText: citationWebsiteUrl ? websiteHighlightText : "",
      claimText: citationFocus?.claimText,
      questionText: userPrompt,
    });
  }, [activeWebsiteUrl, citationFocus?.claimText, citationWebsiteUrl, userPrompt, websiteHighlightText]);

  const citationRawUrl = useMemo(() => {
    if (!citationFocus?.fileId) {
      return null;
    }
    return buildRawFileUrl(citationFocus.fileId, {
      indexId: typeof indexId === "number" ? indexId : undefined,
    });
  }, [citationFocus, indexId]);
  const citationUsesWebsite =
    citationFocus?.sourceType === "website" || (Boolean(citationWebsiteUrl) && !citationRawUrl);
  const citationOpenUrl = citationUsesWebsite
    ? citationWebsiteUrl || activeWebsiteUrl
    : citationRawUrl || "";
  const citationSourceLower = String(citationFocus?.sourceName || "").toLowerCase();
  const citationHasPageHint = Boolean(String(citationFocus?.page || "").trim());
  const citationIsImage = /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(citationSourceLower);
  const citationIsPdf =
    Boolean(citationRawUrl) &&
    !citationUsesWebsite &&
    !citationIsImage &&
    (citationSourceLower.endsWith(".pdf") || citationHasPageHint || !citationSourceLower);

  const mindmapPayload = useMemo(
    () => getMindmapPayload(infoPanel, mindmap),
    [infoPanel, mindmap],
  );
  const hasMindmapPayload = useMemo(() => {
    const nodes = Array.isArray((mindmapPayload as { nodes?: unknown[] }).nodes)
      ? ((mindmapPayload as { nodes?: unknown[] }).nodes as unknown[])
      : [];
    return nodes.length > 0;
  }, [mindmapPayload]);
  const mindmapViewerKey = useMemo(() => {
    const payload = mindmapPayload as {
      root_id?: unknown;
      map_type?: unknown;
      nodes?: Array<{ id?: unknown; title?: unknown }>;
      edges?: Array<{ source?: unknown; target?: unknown }>;
    };
    const mapType = String(payload.map_type || "");
    const root = String(payload.root_id || "");
    const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
    const edges = Array.isArray(payload.edges) ? payload.edges : [];
    const nodeSignature = nodes
      .slice(0, 10)
      .map((node) => `${String(node?.id || "")}:${String(node?.title || "").slice(0, 48)}`)
      .join("|");
    const edgeSignature = edges
      .slice(0, 10)
      .map((edge) => `${String(edge?.source || "")}>${String(edge?.target || "")}`)
      .join("|");
    return `${selectedConversationId || "global"}:${mapType}:${root}:${nodes.length}:${edges.length}:${nodeSignature}:${edgeSignature}`;
  }, [mindmapPayload, selectedConversationId]);

  return (
    <div
      className="min-h-0 bg-white/80 backdrop-blur-xl border-l border-black/[0.06] flex flex-col overflow-hidden"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="px-5 py-4 border-b border-black/[0.06]">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
      </div>

      <div id="html-info-panel" className="flex-1 overflow-y-auto px-5 py-6 space-y-4">
        {hasMindmapPayload ? (
          <div>
            <MindmapViewer
              key={mindmapViewerKey}
              payload={mindmapPayload}
              conversationId={selectedConversationId}
              viewerHeight={viewerHeights.mindmap}
              onAskNode={onAskMindmapNode}
              onSaveMap={(payload) => {
                const storageKey = "maia.saved-mindmaps";
                try {
                  const existing = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, unknown>;
                  const convKey = String(selectedConversationId || "global");
                  const history = Array.isArray(existing[convKey]) ? (existing[convKey] as unknown[]) : [];
                  const next = [...history.slice(-9), { saved_at: new Date().toISOString(), map: payload }];
                  existing[convKey] = next;
                  window.localStorage.setItem(storageKey, JSON.stringify(existing));
                  toast.success("Mind-map saved");
                } catch {
                  toast.error("Unable to save mind-map");
                }
              }}
              onShareMap={(payload) =>
                buildMindmapShareLink({
                  map: payload as unknown as Record<string, unknown>,
                  conversationId: selectedConversationId,
                })
              }
            />
            {renderViewerResizeHandle("mindmap", "mindmap")}
          </div>
        ) : (
          <div className="rounded-xl bg-[#f5f5f7] p-4 text-[12px] text-[#6e6e73]">
            Mind-map is not available for this answer.
          </div>
        )}

        <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
          <div className="mb-2 flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Website preview</p>
              <p
                className="truncate text-[13px] text-[#1d1d1f]"
                title={activeWebsiteUrl || "No website URL found for this answer"}
              >
                {activeWebsiteUrl || "No website URL found for this answer"}
              </p>
            </div>
            {activeWebsiteUrl ? (
              <a
                href={activeWebsiteUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex shrink-0 items-center gap-1 rounded-lg bg-[#1d1d1f] px-2.5 py-1.5 text-[10px] text-white transition-colors hover:bg-[#3a3a3c]"
              >
                <ExternalLink className="h-3 w-3" />
                Open
              </a>
            ) : null}
          </div>
          {citationUsesWebsite && websiteHighlightText ? (
            <div className="mb-2 rounded-lg border border-[#f1d589] bg-[#fff7de] px-2.5 py-2 text-[11px] text-[#5f4b12]">
              <p className="mb-1 text-[10px] uppercase tracking-wide text-[#91720f]">Citation highlight</p>
              <p className="line-clamp-3">{websiteHighlightText}</p>
            </div>
          ) : null}
          {activeWebsiteUrl ? (
            <>
              <div
                className="overflow-hidden rounded-xl border border-black/[0.08] bg-white"
                style={{ height: `${viewerHeights.website}px` }}
              >
                <iframe
                  key={`${activeWebsiteFrameUrl || activeWebsiteUrl}:${websiteHighlightText.slice(0, 96)}`}
                  src={activeWebsiteFrameUrl || activeWebsiteUrl}
                  title="Website preview"
                  className="h-full w-full border-0"
                  sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              </div>
              {renderViewerResizeHandle("website", "website")}
            </>
          ) : (
            <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
              Website preview becomes available when this answer includes a browsable source URL.
            </div>
          )}
        </div>

        {citationFocus ? (
          <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-[#f2f2f7] border border-black/[0.06] flex items-center justify-center shrink-0">
                  <FileText className="w-4 h-4 text-[#3a3a3c]" />
                </div>
                <div className="min-w-0">
                  <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">
                    {citationUsesWebsite ? "Website citation" : "PDF preview"}
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] truncate" title={citationFocus.sourceName}>
                    {citationFocus.sourceName}
                  </p>
                </div>
              </div>
              {citationOpenUrl || citationWebsiteUrl ? (
                <a
                  href={citationOpenUrl || activeWebsiteFrameUrl || citationWebsiteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-[#1d1d1f] text-white text-[10px] hover:bg-[#3a3a3c] transition-colors shrink-0"
                >
                  <ExternalLink className="w-3 h-3" />
                  Open
                </a>
              ) : null}
            </div>

            {citationRawUrl && citationIsPdf ? (
              <CitationPdfPreview
                key={`${citationFocus.fileId || "file"}:${citationFocus.page || "1"}:${String(citationFocus.extract || "").slice(0, 64)}`}
                fileUrl={citationRawUrl}
                page={citationFocus.page}
                highlightText={citationFocus.extract || citationFocus.claimText || ""}
                highlightQuery={citationFocus.claimText}
                highlightBoxes={citationFocus.highlightBoxes}
                viewerHeight={viewerHeights.citation}
              />
            ) : null}

            {citationRawUrl && citationIsImage ? (
              <div
                className="w-full rounded-xl border border-black/[0.08] bg-white overflow-hidden flex items-center justify-center"
                style={{ height: `${Math.max(220, viewerHeights.citation)}px` }}
              >
                <img
                  src={citationRawUrl}
                  alt={citationFocus.sourceName}
                  className="max-w-full max-h-full object-contain"
                />
              </div>
            ) : null}

            {citationUsesWebsite && !citationRawUrl ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                This citation points to a website source. The website preview above is focused on this evidence.
              </div>
            ) : null}

            {!citationUsesWebsite && !citationRawUrl ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                Source preview is unavailable for this file.
              </div>
            ) : null}

            {(citationIsPdf || citationIsImage) ? renderViewerResizeHandle("citation", "citation") : null}

            {onClearCitationFocus ? (
              <button
                type="button"
                onClick={onClearCitationFocus}
                className="mt-2 text-[11px] px-2.5 py-1.5 rounded-lg border border-black/[0.08] text-[#6e6e73] hover:bg-black/[0.03] transition-colors"
              >
                Close preview
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
