import { useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from "react";
import { ExternalLink, FileText } from "lucide-react";
import { toast } from "sonner";

import { buildRawFileUrl } from "../../api/client";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { renderRichText } from "../utils/richText";
import type {
  AgentSourceRecord,
  ChatTurn,
  CitationFocus,
  SourceUsageRecord,
} from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { CitationPdfPreview } from "./CitationPdfPreview";
import { MindmapViewer } from "./MindmapViewer";
import { getMindmapPayload } from "./infoPanelDerived";
import {
  CITATION_ANCHOR_SELECTOR,
  resolveCitationFocusFromAnchor,
  resolveStrengthTier,
} from "./chatMain/citationFocus";

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
const ARTIFACT_URL_PATH_SEGMENTS = new Set([
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

function normalizeHttpUrl(rawValue: unknown): string {
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
}

function normalizeUrlToken(rawValue: unknown): string {
  const value = String(rawValue || "")
    .trim()
    .replace(/^[("'`<\[]+/, "")
    .replace(/[>"'`)\],.;:!?]+$/, "");
  return normalizeHttpUrl(value);
}

function isLikelyLabelArtifactUrl(rawValue: unknown): boolean {
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
    return ARTIFACT_URL_PATH_SEGMENTS.has(token);
  } catch {
    return false;
  }
}

function extractExplicitSourceUrl(rawText: unknown): string {
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
}

function choosePreferredSourceUrl(candidates: Array<string | null | undefined>): string {
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
}

function normalizeEvidenceId(rawValue: unknown): string {
  return String(rawValue || "").trim().toLowerCase();
}

function sourceLooksImage(nameOrUrl: string): boolean {
  return /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(String(nameOrUrl || "").toLowerCase());
}

function evidenceSourceLabel(card: EvidenceCard): string {
  return String(card.source || card.sourceUrl || card.fileId || "Indexed source").trim() || "Indexed source";
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

  const evidenceCards = useMemo(() => parseEvidence(String(infoHtml || "")), [infoHtml]);
  const renderedInfoHtml = useMemo(() => renderRichText(String(infoHtml || "")), [infoHtml]);

  useEffect(() => {
    const container = infoHtmlRef.current;
    if (!container) {
      return;
    }

    const citationAnchors = Array.from(container.querySelectorAll<HTMLAnchorElement>(".chat-answer-html a.citation"));
    for (const anchor of citationAnchors) {
      const tier = resolveStrengthTier(
        Number(anchor.getAttribute("data-strength-tier") || ""),
        Number(anchor.getAttribute("data-strength") || ""),
      );
      if (tier > 0) {
        anchor.setAttribute("data-strength-tier-resolved", String(tier));
      } else {
        anchor.removeAttribute("data-strength-tier-resolved");
      }

      let displayNumber = String(anchor.getAttribute("data-citation-number") || "").trim();
      if (!/^\d{1,4}$/.test(displayNumber)) {
        const fallbackMatch = String(anchor.textContent || "").match(/(\d{1,4})/);
        displayNumber = fallbackMatch?.[1] || "";
        if (displayNumber) {
          anchor.setAttribute("data-citation-number", displayNumber);
        }
      }

      if (!anchor.hasAttribute("href")) {
        anchor.setAttribute("tabindex", "0");
        anchor.setAttribute("role", "button");
      }
    }
  }, [renderedInfoHtml]);

  useEffect(() => {
    const container = infoHtmlRef.current;
    if (!container) {
      return;
    }

    const turnForCitation: ChatTurn = {
      user: String(userPrompt || ""),
      assistant: String(assistantHtml || ""),
      info: String(infoHtml || ""),
      attachments: [],
    };

    const isCitationAnchor = (anchor: HTMLAnchorElement): boolean => {
      const href = String(anchor.getAttribute("href") || "").trim();
      return (
        anchor.classList.contains("citation") ||
        href.startsWith("#evidence-") ||
        anchor.hasAttribute("data-file-id") ||
        anchor.hasAttribute("data-source-url") ||
        anchor.hasAttribute("data-evidence-id")
      );
    };

    const findCitationAnchor = (target: EventTarget | null): HTMLAnchorElement | null => {
      if (!(target instanceof Element)) {
        if (target instanceof Node && target.parentElement) {
          return target.parentElement.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
        }
        return null;
      }
      return target.closest(CITATION_ANCHOR_SELECTOR) as HTMLAnchorElement | null;
    };

    const focusEvidenceDetails = (evidenceId: string | undefined) => {
      const normalizedId = normalizeEvidenceId(evidenceId);
      if (!normalizedId || !/^evidence-[a-z0-9_-]{1,64}$/i.test(normalizedId)) {
        return;
      }
      const detailsNode = container.querySelector<HTMLElement>(`#${normalizedId}`);
      if (!detailsNode) {
        return;
      }
      if (detailsNode.tagName === "DETAILS") {
        (detailsNode as HTMLDetailsElement).open = true;
      }
      detailsNode.scrollIntoView({ block: "nearest" });
    };

    const selectCitationFromAnchor = (anchor: HTMLAnchorElement): boolean => {
      if (!onSelectCitationFocus || !isCitationAnchor(anchor)) {
        return false;
      }
      const resolved = resolveCitationFocusFromAnchor({
        turn: turnForCitation,
        citationAnchor: anchor,
        evidenceCards,
      });
      onSelectCitationFocus(resolved.focus);
      focusEvidenceDetails(resolved.focus.evidenceId);
      return true;
    };

    const onClick = (event: MouseEvent) => {
      const anchor = findCitationAnchor(event.target);
      if (!anchor) {
        return;
      }
      if (!isCitationAnchor(anchor)) {
        return;
      }
      const selected = selectCitationFromAnchor(anchor);
      if (!selected) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const anchor = findCitationAnchor(event.target);
      if (!anchor) {
        return;
      }
      if (!isCitationAnchor(anchor)) {
        return;
      }
      const selected = selectCitationFromAnchor(anchor);
      if (!selected) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
    };

    container.addEventListener("click", onClick);
    container.addEventListener("keydown", onKeyDown);
    return () => {
      container.removeEventListener("click", onClick);
      container.removeEventListener("keydown", onKeyDown);
    };
  }, [assistantHtml, evidenceCards, infoHtml, onSelectCitationFocus, userPrompt]);

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
              <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Citations and evidence</p>
              <p className="truncate text-[13px] text-[#1d1d1f]" title={`${evidenceCards.length} evidence entries`}>
                {evidenceCards.length ? `${evidenceCards.length} evidence entries indexed` : "No evidence entries found"}
              </p>
            </div>
          </div>

          {renderedInfoHtml.trim() ? (
            <div
              ref={infoHtmlRef}
              className="max-h-[500px] overflow-auto rounded-xl border border-black/[0.08] bg-white p-3"
            >
              <div
                className="chat-answer-html assistantAnswerBody info-panel-answer-html text-[13px] leading-[1.5] text-[#1d1d1f]"
                dangerouslySetInnerHTML={{ __html: renderedInfoHtml }}
              />
            </div>
          ) : (
            <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
              This run did not provide rendered evidence HTML.
            </div>
          )}

          {evidenceCards.length ? (
            <div className="mt-3 space-y-2">
              {evidenceCards.slice(0, 8).map((card, index) => {
                const refLabel = String(index + 1);
                const sourceLabel = evidenceSourceLabel(card);
                const snippet = String(card.extract || card.title || "No extract available for this citation.")
                  .replace(/\s+/g, " ")
                  .trim();
                const trimmedSnippet =
                  snippet.length > 210 ? `${snippet.slice(0, 210).trimEnd()}...` : snippet;
                return (
                  <button
                    key={`${card.id || `evidence-${index + 1}`}:${sourceLabel}`}
                    type="button"
                    onClick={() => selectEvidenceCard(card, index)}
                    className="w-full rounded-xl border border-black/[0.06] bg-white px-3 py-2 text-left hover:bg-[#f8f9fc] transition-colors"
                    title={sourceLabel}
                  >
                    <div className="mb-1 flex items-center gap-2 text-[11px] text-[#5f6472]">
                      <span className="rounded-full border border-[#ccd3e2] bg-[#f5f7fb] px-2 py-0.5 font-semibold text-[#2f3a51]">
                        [{refLabel}]
                      </span>
                      <span className="truncate">{sourceLabel}</span>
                      {card.page ? (
                        <span className="shrink-0 rounded-full border border-black/[0.08] bg-white px-1.5 py-0.5 text-[#6e6e73]">
                          p. {card.page}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-[12px] leading-[1.45] text-[#1e2532]">{trimmedSnippet || "No extract available."}</p>
                  </button>
                );
              })}
            </div>
          ) : null}
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
                    {citationUsesWebsite ? "Website citation" : "Citation preview"}
                  </p>
                  <p className="text-[13px] text-[#1d1d1f] truncate" title={citationFocus.sourceName}>
                    {citationFocus.sourceName}
                  </p>
                </div>
              </div>
              {citationOpenUrl ? (
                <a
                  href={citationOpenUrl}
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

            {citationUsesWebsite ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#3a3a3c] space-y-2">
                <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Website extract</p>
                <p className="leading-[1.45]">
                  {String(citationFocus.extract || citationFocus.claimText || "Website citation selected.")
                    .replace(/\s+/g, " ")
                    .trim()}
                </p>
                {citationWebsiteUrl ? (
                  <a
                    href={citationWebsiteUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-[11px] text-[#0a66d9] hover:text-[#0750ab]"
                  >
                    <ExternalLink className="w-3 h-3" />
                    Open website source
                  </a>
                ) : null}
              </div>
            ) : null}

            {!citationUsesWebsite && !citationRawUrl ? (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                Source preview is unavailable for this citation.
              </div>
            ) : null}

            {citationIsPdf || citationIsImage ? renderViewerResizeHandle("citation", "citation") : null}

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
