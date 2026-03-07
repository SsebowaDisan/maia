import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { toast } from "sonner";

import { buildRawFileUrl } from "../../api/client";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { renderRichText } from "../utils/richText";
import type { AgentSourceRecord, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { MindmapViewer } from "./MindmapViewer";
import { getMindmapPayload } from "./infoPanelDerived";
import { CitationPreviewPanel } from "./infoPanel/CitationPreviewPanel";
import { EvidenceCardsList } from "./infoPanel/EvidenceCardsList";
import { useCitationAnchorBinding } from "./infoPanel/useCitationAnchorBinding";
import {
  choosePreferredSourceUrl,
  evidenceSourceLabel,
  extractExplicitSourceUrl,
  normalizeEvidenceId,
  normalizeHttpUrl,
  sourceLooksImage,
} from "./infoPanel/urlHelpers";

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

type ViewerHeightKey = "mindmap" | "citation";

type ViewerHeights = {
  mindmap: number;
  citation: number;
};

const VIEWER_HEIGHT_STORAGE_KEY = "maia.info-panel.viewer-heights.v2";
const DEFAULT_VIEWER_HEIGHTS: ViewerHeights = {
  mindmap: 520,
  citation: 420,
};
const VIEWER_HEIGHT_LIMITS: Record<ViewerHeightKey, { min: number; max: number }> = {
  mindmap: { min: 260, max: 1000 },
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
  assistantHtml = "",
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const [viewerHeights, setViewerHeights] = useState<ViewerHeights>(() => loadViewerHeights());
  const dragViewerRef = useRef<ViewerHeightKey | null>(null);
  const dragStartYRef = useRef(0);
  const dragStartHeightRef = useRef(0);
  const dragCleanupRef = useRef<(() => void) | null>(null);
  const infoHtmlRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(
    () => () => {
      if (dragCleanupRef.current) {
        dragCleanupRef.current();
        dragCleanupRef.current = null;
      }
    },
    [],
  );

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

  const evidenceCards = useMemo(() => parseEvidence(String(infoHtml || "")), [infoHtml]);
  const renderedInfoHtml = useMemo(() => renderRichText(String(infoHtml || "")), [infoHtml]);

  useCitationAnchorBinding({
    containerRef: infoHtmlRef,
    renderedInfoHtml,
    userPrompt: String(userPrompt || ""),
    assistantHtml: String(assistantHtml || ""),
    infoHtml: String(infoHtml || ""),
    evidenceCards,
    onSelectCitationFocus,
  });

  const citationWebsiteUrl = useMemo(() => {
    const direct = normalizeHttpUrl(citationFocus?.sourceUrl);
    const fromExtract = extractExplicitSourceUrl(citationFocus?.extract || "");
    const sourceNameUrl = normalizeHttpUrl(citationFocus?.sourceName);
    const rankedDirect = choosePreferredSourceUrl([fromExtract, direct, sourceNameUrl]);
    const evidenceId = normalizeEvidenceId(citationFocus?.evidenceId);
    if (evidenceId) {
      const matchedById = evidenceCards.find((card) => normalizeEvidenceId(card.id) === evidenceId);
      const matchedByIdUrl = choosePreferredSourceUrl([
        extractExplicitSourceUrl(matchedById?.extract || ""),
        normalizeHttpUrl(matchedById?.sourceUrl),
      ]);
      if (matchedByIdUrl) {
        return choosePreferredSourceUrl([matchedByIdUrl, rankedDirect]);
      }
    }
    return rankedDirect || "";
  }, [citationFocus, evidenceCards]);

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
  const citationOpenUrl = citationUsesWebsite ? citationWebsiteUrl : citationRawUrl || "";
  const citationSourceLower = String(citationFocus?.sourceName || "").toLowerCase();
  const citationHasPageHint = Boolean(String(citationFocus?.page || "").trim());
  const citationIsImage =
    Boolean(citationRawUrl) &&
    !citationUsesWebsite &&
    (sourceLooksImage(citationSourceLower) || sourceLooksImage(citationRawUrl));
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

  const selectEvidenceCard = (card: EvidenceCard, index: number) => {
    if (!onSelectCitationFocus) {
      return;
    }
    const sourceUrl = normalizeHttpUrl(card.sourceUrl);
    onSelectCitationFocus({
      fileId: card.fileId,
      sourceUrl: sourceUrl || undefined,
      sourceType: sourceUrl && !sourceLooksImage(sourceUrl) ? "website" : "file",
      sourceName: evidenceSourceLabel(card),
      page: card.page,
      extract: String(card.extract || card.title || "No extract available for this citation.")
        .replace(/\s+/g, " ")
        .trim(),
      evidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
      highlightBoxes: card.highlightBoxes,
      strengthScore: card.strengthScore,
      strengthTier: card.strengthTier,
      matchQuality: card.matchQuality,
      unitId: card.unitId,
      charStart: card.charStart,
      charEnd: card.charEnd,
    });
  };

  return (
    <div
      className="flex min-h-0 flex-col overflow-hidden border-l border-black/[0.06] bg-white/80 backdrop-blur-xl"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="border-b border-black/[0.06] px-5 py-4">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
      </div>

      <div id="html-info-panel" className="flex-1 space-y-4 overflow-y-auto px-5 py-6">
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
              <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Evidence rail</p>
              <p className="truncate text-[13px] text-[#1d1d1f]" title={`${evidenceCards.length} evidence entries`}>
                {evidenceCards.length ? `${evidenceCards.length} evidence entries indexed` : "No evidence entries found"}
              </p>
            </div>
          </div>

          <EvidenceCardsList
            cards={evidenceCards}
            selectedEvidenceId={normalizeEvidenceId(citationFocus?.evidenceId)}
            onSelectCard={selectEvidenceCard}
          />

          <details className="mt-3 rounded-xl border border-black/[0.08] bg-white px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium text-[#4c4c50]">
              Rendered citations and report markup
            </summary>
            {renderedInfoHtml.trim() ? (
              <div
                ref={infoHtmlRef}
                className="mt-2 max-h-[420px] overflow-auto rounded-lg border border-black/[0.06] bg-white p-3"
              >
                <div
                  className="chat-answer-html assistantAnswerBody info-panel-answer-html text-[13px] leading-[1.5] text-[#1d1d1f]"
                  dangerouslySetInnerHTML={{ __html: renderedInfoHtml }}
                />
              </div>
            ) : (
              <div className="mt-2 rounded-lg border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                This run did not provide rendered evidence HTML.
              </div>
            )}
          </details>
        </div>

        {citationFocus ? (
          <CitationPreviewPanel
            citationFocus={citationFocus}
            citationOpenUrl={citationOpenUrl}
            citationRawUrl={citationRawUrl}
            citationUsesWebsite={citationUsesWebsite}
            citationWebsiteUrl={citationWebsiteUrl}
            citationIsPdf={citationIsPdf}
            citationIsImage={citationIsImage}
            citationViewerHeight={viewerHeights.citation}
            onClear={onClearCitationFocus}
            renderResizeHandle={() => renderViewerResizeHandle("citation", "citation")}
          />
        ) : null}
      </div>
    </div>
  );
}
