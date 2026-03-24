import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { AgentActivityEvent, AgentSourceRecord, ChatAttachment, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { MindmapArtifactDialog } from "./MindmapArtifactDialog";
import { TeamConversationTab } from "./agentActivityPanel/TeamConversationTab";
import { getMindmapPayload } from "./infoPanelDerived";
import { CitationPreviewPanel } from "./infoPanel/CitationPreviewPanel";
import { resolveMindmapFocus } from "./infoPanel/mindmapFocus";
import { parseWebReviewSourceMap, resolveWebReviewSource } from "./infoPanel/review/webReviewContent";
import { useResizableViewers } from "./infoPanel/useResizableViewers";
import { useVerificationMemory } from "./infoPanel/useVerificationMemory";
import { resolveCitationOpenUrl, sourceIdForCitation, toCitationFromEvidence } from "./infoPanel/verificationHelpers";
import {
  buildVerificationSources,
  inferPreferredSourceId,
  type VerificationSourceItem,
} from "./infoPanel/verificationModels";
import {
  normalizeEvidenceId,
} from "./infoPanel/urlHelpers";
import { buildMindmapArtifactSummary } from "./mindmapViewer/presentation";
import { toMindmapPayload } from "./mindmapViewer/viewerHelpers";
import { resolvePreferredRunId } from "../utils/runIdSelection";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  userPrompt?: string;
  attachments?: ChatAttachment[];
  assistantHtml?: string;
  infoHtml?: string;
  infoPanel?: Record<string, unknown>;
  mindmap?: Record<string, unknown>;
  activityEvents?: AgentActivityEvent[];
  sourcesUsed?: AgentSourceRecord[];
  webSummary?: Record<string, unknown>;
  sourceUsage?: SourceUsageRecord[];
  activityRunId?: string | null;
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

function findSourceById(sources: VerificationSourceItem[], sourceId: string): VerificationSourceItem | null {
  const normalized = String(sourceId || "").trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  return sources.find((source) => source.id === normalized) || null;
}

export function InfoPanel({
  citationFocus = null,
  selectedConversationId = null,
  userPrompt = "",
  attachments = [],
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  activityEvents = [],
  activityRunId = null,
  sourcesUsed = [],
  sourceUsage = [],
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const { viewerHeights, renderViewerResizeHandle } = useResizableViewers();
  const { memory, updateMemory } = useVerificationMemory(selectedConversationId);
  const contentViewportRef = useRef<HTMLDivElement | null>(null);
  const citationPanelRef = useRef<HTMLDivElement | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [pdfZoom, setPdfZoom] = useState(1);
  const [isMindmapDialogOpen, setIsMindmapDialogOpen] = useState(false);
  const [citationAutoHeight, setCitationAutoHeight] = useState(0);

  const evidenceCards = useMemo(
    () =>
      parseEvidence(String(infoHtml || ""), {
        infoPanel: infoPanel as Record<string, unknown>,
        userPrompt: String(userPrompt || ""),
        promptAttachments: Array.isArray(attachments) ? attachments : [],
      }),
    [attachments, infoHtml, infoPanel, userPrompt],
  );

  const { sources, evidenceBySource } = useMemo(
    () =>
      buildVerificationSources({
        evidenceCards,
        sourcesUsed,
        sourceUsage,
      }),
    [evidenceCards, sourceUsage, sourcesUsed],
  );

  const preferredSourceId = useMemo(
    () =>
      inferPreferredSourceId({
        citationFocus,
        sources,
        fallback: memory.selectedSourceId,
      }),
    [citationFocus, memory.selectedSourceId, sources],
  );

  useEffect(() => {
    if (!selectedSourceId && preferredSourceId) {
      setSelectedSourceId(preferredSourceId);
      return;
    }
    if (selectedSourceId && !findSourceById(sources, selectedSourceId) && preferredSourceId) {
      setSelectedSourceId(preferredSourceId);
    }
  }, [preferredSourceId, selectedSourceId, sources]);

  useEffect(() => {
    if (memory.reviewZoom > 0) {
      setPdfZoom(memory.reviewZoom);
    }
  }, [memory.reviewZoom]);

  const selectedSource = useMemo(
    () => findSourceById(sources, selectedSourceId) || findSourceById(sources, preferredSourceId),
    [preferredSourceId, selectedSourceId, sources],
  );

  const sourceEvidence = useMemo(() => {
    if (!selectedSource?.id) {
      return evidenceCards;
    }
    return evidenceBySource[selectedSource.id] || [];
  }, [evidenceBySource, evidenceCards, selectedSource?.id]);

  const activeEvidenceId = normalizeEvidenceId(citationFocus?.evidenceId || memory.selectedEvidenceId || "");
  const activeEvidenceIndex = useMemo(() => {
    if (!activeEvidenceId) {
      return evidenceCards.length ? 0 : -1;
    }
    return evidenceCards.findIndex((card) => normalizeEvidenceId(card.id) === activeEvidenceId);
  }, [activeEvidenceId, evidenceCards]);

  const activeEvidenceCard = activeEvidenceIndex >= 0 ? evidenceCards[activeEvidenceIndex] : evidenceCards[0];
  const activeCitation = citationFocus || (activeEvidenceCard ? toCitationFromEvidence(activeEvidenceCard, activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0) : null);
  const activeCitationSourceKey = useMemo(() => sourceIdForCitation(activeCitation), [activeCitation]);

  const preferredCitationPage = useMemo(() => {
    const explicitCitationPage = String(activeCitation?.page || "").trim();
    if (explicitCitationPage) {
      return undefined;
    }
    if (!activeCitationSourceKey) {
      return undefined;
    }
    const remembered = Number(memory.reviewPageBySource[activeCitationSourceKey] || 0);
    if (!Number.isFinite(remembered) || remembered <= 0) {
      return undefined;
    }
    return String(Math.floor(remembered));
  }, [activeCitationSourceKey, memory.reviewPageBySource]);

  const citationOpenState = useMemo(
    () =>
      resolveCitationOpenUrl({
        citation: activeCitation,
        evidenceCards,
        indexId,
      }),
    [activeCitation, evidenceCards, indexId],
  );

  const webReviewSourceMap = useMemo(
    () => parseWebReviewSourceMap(infoPanel as Record<string, unknown>),
    [infoPanel],
  );
  const activeWebReviewSource = useMemo(
    () =>
      resolveWebReviewSource({
        sourceMap: webReviewSourceMap,
        sourceId: selectedSource?.id || activeCitationSourceKey || "",
        sourceUrl: citationOpenState.citationWebsiteUrl || selectedSource?.url || activeCitation?.sourceUrl || "",
        sourceTitle: activeCitation?.sourceName || selectedSource?.title || "Website source",
        evidenceCards: sourceEvidence,
      }),
    [
      activeCitation?.sourceName,
      activeCitation?.sourceUrl,
      activeCitationSourceKey,
      citationOpenState.citationWebsiteUrl,
      selectedSource?.id,
      selectedSource?.title,
      selectedSource?.url,
      sourceEvidence,
      webReviewSourceMap,
    ],
  );

  const mindmapPayload = useMemo(() => getMindmapPayload(infoPanel, mindmap), [infoPanel, mindmap]);
  const hasMindmapPayload = Array.isArray((mindmapPayload as { nodes?: unknown[] }).nodes)
    ? ((mindmapPayload as { nodes?: unknown[] }).nodes as unknown[]).length > 0
    : false;
  const workspaceGraphPayload = mindmapPayload;
  const typedMindmapPayload = useMemo(
    () => toMindmapPayload(workspaceGraphPayload as Record<string, unknown>),
    [workspaceGraphPayload],
  );
  const conversationRunId = useMemo(
    () => resolvePreferredRunId(activityRunId, activityEvents),
    [activityEvents, activityRunId],
  );
  const showTeamConversation = Boolean(conversationRunId) || activityEvents.length > 0;
  const showEvidenceSurfaces = Boolean(citationFocus);
  const mindmapSummary = useMemo(
    () => buildMindmapArtifactSummary(typedMindmapPayload),
    [typedMindmapPayload],
  );
  const effectiveCitationViewerHeight = useMemo(() => {
    if (citationAutoHeight > 0) {
      return citationAutoHeight;
    }
    return viewerHeights.citation;
  }, [citationAutoHeight, viewerHeights.citation]);

  const recomputeCitationAutoHeight = useCallback(() => {
    const viewportNode = contentViewportRef.current;
    const citationNode = citationPanelRef.current;
    if (!viewportNode || !citationNode) {
      return;
    }
    const viewportRect = viewportNode.getBoundingClientRect();
    const citationRect = citationNode.getBoundingClientRect();

    // pb-10 (40px) keeps breathing room above the bottom gradient.
    const viewportBottomPadding = 40;
    // CitationPreviewPanel has chrome outside the website/PDF viewer area.
    const previewChromeOffset = 96;
    const availableViewerHeight =
      viewportRect.bottom - citationRect.top - viewportBottomPadding - previewChromeOffset;
    const nextHeight = Math.max(320, Math.min(1000, Math.floor(availableViewerHeight)));
    setCitationAutoHeight((current) => (Math.abs(current - nextHeight) > 1 ? nextHeight : current));
  }, []);

  useEffect(() => {
    if (!activeCitation) {
      setCitationAutoHeight(0);
      return;
    }

    let frameId = 0;
    const scheduleRecompute = () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      frameId = window.requestAnimationFrame(() => {
        recomputeCitationAutoHeight();
      });
    };

    scheduleRecompute();

    const viewportNode = contentViewportRef.current;
    if (viewportNode) {
      viewportNode.addEventListener("scroll", scheduleRecompute, { passive: true });
    }
    window.addEventListener("resize", scheduleRecompute);

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(scheduleRecompute);
      if (viewportNode) {
        observer.observe(viewportNode);
      }
      if (citationPanelRef.current) {
        observer.observe(citationPanelRef.current);
      }
    }

    return () => {
      if (frameId) {
        window.cancelAnimationFrame(frameId);
      }
      if (viewportNode) {
        viewportNode.removeEventListener("scroll", scheduleRecompute);
      }
      window.removeEventListener("resize", scheduleRecompute);
      observer?.disconnect();
    };
  }, [activeCitation, recomputeCitationAutoHeight]);

  const selectEvidence = (card: EvidenceCard, index: number) => {
    const nextCitation = toCitationFromEvidence(card, index);
    const sourceId = sourceIdForCitation(nextCitation);
    if (sourceId) {
      setSelectedSourceId(sourceId);
      updateMemory({ selectedSourceId: sourceId });
    }
    updateMemory({
      selectedEvidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
    });
    onSelectCitationFocus?.(nextCitation);
  };

  const selectSource = (sourceId: string) => {
    setSelectedSourceId(sourceId);
    const firstEvidence = (evidenceBySource[sourceId] || [])[0];
    updateMemory({
      selectedSourceId: sourceId,
      selectedEvidenceId: normalizeEvidenceId(firstEvidence?.id || ""),
    });
  };

  const jumpToNeighborEvidence = (offset: number) => {
    if (!evidenceCards.length) {
      return;
    }
    const current = activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0;
    const next = Math.max(0, Math.min(evidenceCards.length - 1, current + offset));
    const target = evidenceCards[next];
    if (!target) {
      return;
    }
    selectEvidence(target, next);
  };

  const handleMindmapFocus = (payload: {
    nodeId: string;
    title: string;
    text: string;
    pageRef?: string;
    sourceId?: string;
    sourceName?: string;
  }) => {
    const resolved = resolveMindmapFocus({
      node: payload,
      sources,
      evidenceBySource,
    });
    if (resolved.sourceId) {
      selectSource(resolved.sourceId);
    }
    if (resolved.evidenceCard) {
      selectEvidence(resolved.evidenceCard, resolved.evidenceIndex);
    }
  };

  const handleSaveMindmap = (payload: Record<string, unknown>) => {
    const storageKey = "maia.saved-mindmaps";
    try {
      const existing = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, unknown>;
      const conversationKey = String(selectedConversationId || "global");
      const history = Array.isArray(existing[conversationKey]) ? (existing[conversationKey] as unknown[]) : [];
      existing[conversationKey] = [...history.slice(-9), { saved_at: new Date().toISOString(), map: payload }];
      window.localStorage.setItem(storageKey, JSON.stringify(existing));
      toast.success("Mind-map saved");
    } catch {
      toast.error("Unable to save mind-map");
    }
  };

  const handleShareMindmap = (payload: Record<string, unknown>) =>
    buildMindmapShareLink({
      map: payload,
      conversationId: selectedConversationId,
    });

  return (
    <div
      className="flex min-h-0 flex-col overflow-hidden rounded-[28px] border border-black/[0.06] bg-[#f6f6f7] shadow-[0_14px_40px_rgba(15,23,42,0.06)]"
      style={{ width: `${Math.round(width)}px` }}
    >
      <div className="border-b border-black/[0.06] px-5 py-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
            {showEvidenceSurfaces ? "Evidence" : showTeamConversation ? "Live Team Thread" : "Dialogue"}
          </p>
          <h3 className="mt-1 text-[20px] font-semibold tracking-[-0.02em] text-[#17171b]">
            {showEvidenceSurfaces ? "Sources" : showTeamConversation ? "Team Conversation" : "Conversation"}
          </h3>
        </div>
      </div>

      <div className="relative min-h-0 flex-1">
        <div
          ref={contentViewportRef}
          className={`h-full overflow-y-auto overscroll-none px-5 ${
            showEvidenceSurfaces ? "space-y-4 pb-10 pt-5" : "pb-4 pt-4"
          }`}
        >
          {showTeamConversation ? (
            <div className={showEvidenceSurfaces ? "" : "flex h-full min-h-0 flex-col"}>
              <TeamConversationTab runId={conversationRunId} events={activityEvents} />
            </div>
          ) : null}

          {showEvidenceSurfaces ? (
            <section className="space-y-3 rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#7b8598]">
                  {mindmapSummary?.presentation.eyebrow || "Research artifact"}
                </p>
                <h4 className="mt-1 text-[16px] font-semibold tracking-[-0.02em] text-[#17171b]">
                  {mindmapSummary?.presentation.label || "Knowledge map"}
                </h4>
                <p className="mt-1 text-[12px] leading-5 text-[#6b6b70]">
                  {mindmapSummary?.presentation.summary ||
                    "Open a dedicated artifact surface to inspect the answer map without crowding the Sources panel."}
                </p>
              </div>
              {hasMindmapPayload ? (
                <button
                  type="button"
                  onClick={() => setIsMindmapDialogOpen(true)}
                  className="shrink-0 rounded-full bg-[#17171b] px-3 py-2 text-[11px] font-semibold text-white transition-colors hover:bg-[#2a2a30]"
                >
                  Open map
                </button>
              ) : null}
            </div>

            {hasMindmapPayload ? (
              <div className="rounded-2xl border border-black/[0.06] bg-white/80 p-3">
                <div className="flex flex-wrap gap-2">
                  {mindmapSummary?.availableMapTypes.map((mapType) => (
                    <span
                      key={mapType}
                      className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]"
                    >
                      {mapType === "context_mindmap"
                        ? "Sources"
                        : mapType === "work_graph"
                          ? "Execution"
                          : mapType === "evidence"
                            ? "Evidence"
                            : "Concept"}
                    </span>
                  ))}
                  {mindmapSummary?.nodeCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.nodeCount} nodes
                    </span>
                  ) : null}
                  {mindmapSummary?.sourceCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.sourceCount} sources
                    </span>
                  ) : null}
                  {mindmapSummary?.actionCount ? (
                    <span className="rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[11px] font-medium text-[#4a4a50]">
                      {mindmapSummary.actionCount} actions
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 text-[12px] leading-5 text-[#6b6b70]">
                  The full map now opens in its own artifact surface so the right panel can stay focused on source preview.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-black/[0.08] bg-white/65 p-4 text-[12px] leading-5 text-[#6e6e73]">
                No mindmap artifact was produced for this answer yet. Research-heavy or comparative questions will populate this surface when the backend emits a structured map.
              </div>
            )}
            </section>
          ) : !showTeamConversation ? (
            <section className="rounded-2xl border border-[#e4e7ec] bg-white px-4 py-3 text-[12px] text-[#667085]">
              Click a citation in the assistant answer to open source evidence in this panel.
            </section>
          ) : null}

          {/* Citation page preview */}
          {showEvidenceSurfaces && activeCitation ? (
            <div ref={citationPanelRef}>
              <CitationPreviewPanel
                citationFocus={activeCitation}
                citationOpenUrl={citationOpenState.citationOpenUrl}
                citationRawUrl={citationOpenState.citationRawUrl}
                citationUsesWebsite={citationOpenState.citationUsesWebsite}
                citationWebsiteUrl={citationOpenState.citationWebsiteUrl}
                citationIsPdf={citationOpenState.citationIsPdf}
                citationIsImage={citationOpenState.citationIsImage}
                citationViewerHeight={effectiveCitationViewerHeight}
                reviewQuery={userPrompt || activeCitation?.claimText || ""}
                preferredPage={preferredCitationPage}
                webReviewSource={activeWebReviewSource}
                hasPreviousEvidence={activeEvidenceIndex > 0}
                hasNextEvidence={activeEvidenceIndex >= 0 && activeEvidenceIndex < evidenceCards.length - 1}
                onPreviousEvidence={() => jumpToNeighborEvidence(-1)}
                onNextEvidence={() => jumpToNeighborEvidence(1)}
                pdfZoom={pdfZoom}
                onPdfZoomChange={(next) => {
                  setPdfZoom(next);
                  updateMemory({ reviewZoom: next });
                }}
                onPdfPageChange={(nextPage) => {
                  if (!activeCitationSourceKey || nextPage <= 0) {
                    return;
                  }
                  const previous = Number(memory.reviewPageBySource[activeCitationSourceKey] || 0);
                  if (previous === nextPage) {
                    return;
                  }
                  updateMemory({
                    reviewPageBySource: {
                      ...memory.reviewPageBySource,
                      [activeCitationSourceKey]: nextPage,
                    },
                  });
                }}
                onClear={onClearCitationFocus}
                renderResizeHandle={() => renderViewerResizeHandle("citation", "citation")}
              />
            </div>
          ) : showEvidenceSurfaces && sources.length > 0 ? (
            <div className="rounded-xl border border-black/[0.06] bg-white p-4 text-center text-[12px] text-[#6e6e73]">
              Click any citation in the answer to preview the source page here.
            </div>
          ) : null}
        </div>
        {showEvidenceSurfaces ? (
          <div className="pointer-events-none absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-[#f6f6f7] via-[#f6f6f7]/92 to-transparent" />
        ) : null}
      </div>

      {/* Footer — matches sidebar footer and composer pill height (60px) */}
      <div className="shrink-0 border-t border-black/[0.06] bg-[#f6f6f7] px-3 py-3">
        <div className="flex h-9 items-center gap-2 rounded-xl border border-black/[0.08] bg-white px-3 text-[12px] text-[#6e6e73]">
          <span className="truncate">
            {showEvidenceSurfaces
              ? sources.length > 0
                ? `${sources.length} source${sources.length !== 1 ? "s" : ""}`
                : "No sources"
              : showTeamConversation
                ? "Live teammate thread"
                : "No conversation yet"}
          </span>
        </div>
      </div>

      <MindmapArtifactDialog
        open={isMindmapDialogOpen}
        onOpenChange={setIsMindmapDialogOpen}
        payload={workspaceGraphPayload as Record<string, unknown>}
        conversationId={selectedConversationId}
        onAskNode={onAskMindmapNode}
        onFocusNode={handleMindmapFocus}
        onSaveMap={(payload) => handleSaveMindmap(payload as unknown as Record<string, unknown>)}
        onShareMap={(payload) => handleShareMindmap(payload as unknown as Record<string, unknown>)}
      />
    </div>
  );
}
