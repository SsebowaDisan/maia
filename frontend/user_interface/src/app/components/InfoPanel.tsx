import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import type { AgentActivityEvent, AgentSourceRecord, ChatAttachment, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { MindmapViewer } from "./MindmapViewer";
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
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [pdfZoom, setPdfZoom] = useState(1);

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

  return (
    <div className="flex min-h-0 flex-col overflow-hidden border-l border-black/[0.06] bg-white/80 backdrop-blur-xl" style={{ width: `${Math.round(width)}px` }}>
      <div className="border-b border-black/[0.06] px-5 py-4">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Sources</h3>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
        {/* Mindmap */}
        <section className="space-y-2 rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Context Mindmap</p>
          {hasMindmapPayload ? (
            <div>
              <MindmapViewer
                payload={workspaceGraphPayload as Record<string, unknown>}
                conversationId={selectedConversationId}
                viewerHeight={viewerHeights.mindmap}
                onAskNode={onAskMindmapNode}
                onFocusNode={handleMindmapFocus}
                onSaveMap={(payload) => {
                  const storageKey = "maia.saved-mindmaps";
                  try {
                    const existing = JSON.parse(window.localStorage.getItem(storageKey) || "{}") as Record<string, unknown>;
                    const convKey = String(selectedConversationId || "global");
                    const history = Array.isArray(existing[convKey]) ? (existing[convKey] as unknown[]) : [];
                    existing[convKey] = [...history.slice(-9), { saved_at: new Date().toISOString(), map: payload }];
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
            <div className="rounded-xl bg-[#f5f5f7] p-3 text-[12px] text-[#6e6e73]">
              Context mindmap is not available for this answer yet.
            </div>
          )}
        </section>


        {/* Citation page preview */}
        {activeCitation ? (
          <CitationPreviewPanel
            citationFocus={activeCitation}
            citationOpenUrl={citationOpenState.citationOpenUrl}
            citationRawUrl={citationOpenState.citationRawUrl}
            citationUsesWebsite={citationOpenState.citationUsesWebsite}
            citationWebsiteUrl={citationOpenState.citationWebsiteUrl}
            citationIsPdf={citationOpenState.citationIsPdf}
            citationIsImage={citationOpenState.citationIsImage}
            citationViewerHeight={viewerHeights.citation}
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
        ) : sources.length > 0 ? (
          <div className="rounded-xl border border-black/[0.06] bg-white p-4 text-center text-[12px] text-[#6e6e73]">
            Click any citation in the answer to preview the source page here.
          </div>
        ) : null}
      </div>
    </div>
  );
}
