import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useShallow } from "zustand/react/shallow";

import type { AgentActivityEvent, AgentSourceRecord, CitationFocus, SourceUsageRecord } from "../types";
import { parseEvidence } from "../utils/infoInsights";
import type { EvidenceCard } from "../utils/infoInsights";
import { buildMindmapShareLink } from "../utils/mindmapDeepLink";
import { MindmapViewer } from "./MindmapViewer";
import { getMindmapPayload } from "./infoPanelDerived";
import { CitationPreviewPanel } from "./infoPanel/CitationPreviewPanel";
import { EvidenceCardsList } from "./infoPanel/EvidenceCardsList";
import { VerificationComparePanel } from "./infoPanel/VerificationComparePanel";
import { VerificationFooter } from "./infoPanel/VerificationFooter";
import { VerificationSourceBar } from "./infoPanel/VerificationSourceBar";
import { VerificationSourceList } from "./infoPanel/VerificationSourceList";
import { VerificationTabBar } from "./infoPanel/VerificationTabBar";
import { VerificationTrailPanel } from "./infoPanel/VerificationTrailPanel";
import { useResizableViewers } from "./infoPanel/useResizableViewers";
import { type VerificationTab, useVerificationMemory } from "./infoPanel/useVerificationMemory";
import { resolveCitationOpenUrl, sourceIdForCitation, toCitationFromEvidence } from "./infoPanel/verificationHelpers";
import {
  buildVerificationSources,
  filterEvidenceByConcept,
  inferPreferredSourceId,
  summarizeEvidenceQuality,
  type VerificationSourceItem,
} from "./infoPanel/verificationModels";
import {
  normalizeEvidenceId,
} from "./infoPanel/urlHelpers";
import { WorkGraphViewer } from "./workGraph/WorkGraphViewer";
import { buildWorkGraphMindmapPayload, startWorkGraphRunSync, useWorkGraphStore } from "./workGraph/useWorkGraphStore";

interface InfoPanelProps {
  citationFocus?: CitationFocus | null;
  selectedConversationId?: string | null;
  userPrompt?: string;
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
  infoHtml = "",
  infoPanel = {},
  mindmap = {},
  activityEvents = [],
  sourcesUsed = [],
  sourceUsage = [],
  activityRunId = null,
  indexId = null,
  onClearCitationFocus,
  onSelectCitationFocus,
  onAskMindmapNode,
  width = 340,
}: InfoPanelProps) {
  const { viewerHeights, renderViewerResizeHandle } = useResizableViewers();
  const { memory, updateMemory } = useVerificationMemory(selectedConversationId);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [pdfZoom, setPdfZoom] = useState(1);

  const evidenceCards = useMemo(
    () =>
      parseEvidence(String(infoHtml || ""), {
        infoPanel: infoPanel as Record<string, unknown>,
      }),
    [infoHtml, infoPanel],
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

  const filteredEvidence = useMemo(() => filterEvidenceByConcept(sourceEvidence, searchQuery), [searchQuery, sourceEvidence]);
  const visibleEvidence = filteredEvidence.length || !searchQuery ? filteredEvidence : [];
  const evidenceRows = useMemo(() => (searchQuery ? visibleEvidence : sourceEvidence), [searchQuery, sourceEvidence, visibleEvidence]);

  const activeEvidenceId = normalizeEvidenceId(citationFocus?.evidenceId || memory.selectedEvidenceId || "");
  const activeEvidenceIndex = useMemo(() => {
    if (!activeEvidenceId) {
      return evidenceRows.length ? 0 : -1;
    }
    return evidenceRows.findIndex((card) => normalizeEvidenceId(card.id) === activeEvidenceId);
  }, [activeEvidenceId, evidenceRows]);

  const activeEvidenceCard = activeEvidenceIndex >= 0 ? evidenceRows[activeEvidenceIndex] : evidenceRows[0];
  const activeCitation = citationFocus || (activeEvidenceCard ? toCitationFromEvidence(activeEvidenceCard, activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0) : null);

  const citationOpenState = useMemo(
    () =>
      resolveCitationOpenUrl({
        citation: activeCitation,
        evidenceCards,
        indexId,
      }),
    [activeCitation, evidenceCards, indexId],
  );

  const qualitySummary = useMemo(() => summarizeEvidenceQuality(evidenceRows.length ? evidenceRows : evidenceCards), [evidenceCards, evidenceRows]);

  const mindmapPayload = useMemo(() => getMindmapPayload(infoPanel, mindmap), [infoPanel, mindmap]);
  const inferredRunId = useMemo(() => {
    const direct = String(activityRunId || "").trim();
    if (direct) {
      return direct;
    }
    for (let index = activityEvents.length - 1; index >= 0; index -= 1) {
      const candidate = String(activityEvents[index]?.run_id || "").trim();
      if (candidate) {
        return candidate;
      }
    }
    return "";
  }, [activityEvents, activityRunId]);

  const workGraphSlice = useWorkGraphStore(
    useShallow((state) => ({
      runId: state.runId,
      title: state.title,
      rootId: state.rootId,
      schema: state.schema,
      nodes: state.nodes,
      edges: state.edges,
      filters: state.filters,
      error: state.error,
    })),
  );
  const applyWorkGraphActivityEvents = useWorkGraphStore((state) => state.applyActivityEvents);
  const resetWorkGraph = useWorkGraphStore((state) => state.reset);

  useEffect(() => {
    if (!inferredRunId) {
      resetWorkGraph();
      return;
    }
    const stopSync = startWorkGraphRunSync(inferredRunId);
    return () => stopSync();
  }, [inferredRunId, resetWorkGraph]);

  useEffect(() => {
    if (activityEvents.length) {
      applyWorkGraphActivityEvents(activityEvents);
    }
  }, [activityEvents, applyWorkGraphActivityEvents]);

  const workGraphPayload = useMemo(
    () =>
      buildWorkGraphMindmapPayload({
        runId: workGraphSlice.runId,
        title: workGraphSlice.title,
        rootId: workGraphSlice.rootId,
        schema: workGraphSlice.schema,
        nodes: workGraphSlice.nodes,
        edges: workGraphSlice.edges,
        filters: workGraphSlice.filters,
      }),
    [workGraphSlice.edges, workGraphSlice.filters, workGraphSlice.nodes, workGraphSlice.rootId, workGraphSlice.runId, workGraphSlice.schema, workGraphSlice.title],
  );
  const hasWorkGraphPayload = Boolean(workGraphPayload && workGraphPayload.nodes.length > 0);
  const hasMindmapPayload = Array.isArray((mindmapPayload as { nodes?: unknown[] }).nodes)
    ? ((mindmapPayload as { nodes?: unknown[] }).nodes as unknown[]).length > 0
    : false;
  const workspaceGraphPayload = workGraphPayload || mindmapPayload;

  const setVerificationTab = (nextTab: VerificationTab) => updateMemory({ verificationTab: nextTab });
  const setEvidenceMode = (nextMode: "exact" | "context") => updateMemory({ evidenceMode: nextMode });

  const selectEvidence = (card: EvidenceCard, index: number) => {
    const nextCitation = toCitationFromEvidence(card, index);
    const sourceId = sourceIdForCitation(nextCitation);
    if (sourceId) {
      setSelectedSourceId(sourceId);
      updateMemory({ selectedSourceId: sourceId });
    }
    updateMemory({
      selectedEvidenceId: normalizeEvidenceId(card.id) || `evidence-${index + 1}`,
      verificationTab: "review",
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
    if (!evidenceRows.length) {
      return;
    }
    const current = activeEvidenceIndex >= 0 ? activeEvidenceIndex : 0;
    const next = Math.max(0, Math.min(evidenceRows.length - 1, current + offset));
    const target = evidenceRows[next];
    if (!target) {
      return;
    }
    selectEvidence(target, next);
  };

  const inspectWorkGraphEvidence = (payload: { nodeId: string; title: string; evidenceIds: string[]; sceneRefs: string[]; eventRefs: string[] }) => {
    setVerificationTab("evidence");
    const preferredEvidenceId = payload.evidenceIds.find((rawId) => {
      const normalized = normalizeEvidenceId(rawId);
      return normalized ? evidenceCards.some((card) => normalizeEvidenceId(card.id) === normalized) : false;
    });
    if (preferredEvidenceId) {
      const normalized = normalizeEvidenceId(preferredEvidenceId);
      const index = evidenceCards.findIndex((card) => normalizeEvidenceId(card.id) === normalized);
      if (index >= 0) {
        selectEvidence(evidenceCards[index], index);
        return;
      }
    }
    onSelectCitationFocus?.({
      sourceName: payload.title || "Work graph evidence",
      extract: `Inspect evidence linked to node "${payload.title || payload.nodeId}".`,
      evidenceId: normalizeEvidenceId(preferredEvidenceId || "") || undefined,
      graphNodeIds: [payload.nodeId],
      sceneRefs: payload.sceneRefs,
      eventRefs: payload.eventRefs,
    });
  };

  const inspectWorkGraphVerifier = (payload: {
    nodeId: string;
    title: string;
    detail: string;
    status: string;
    confidence: number | null;
    riskReason: string;
    sceneRefs: string[];
    eventRefs: string[];
  }) => {
    setVerificationTab("evidence");
    const confidenceLabel = typeof payload.confidence === "number" && Number.isFinite(payload.confidence) ? `${Math.round(payload.confidence * 100)}%` : "n/a";
    const reason = payload.riskReason || payload.detail || "Verifier review requested for this node.";
    toast.info(`Verifier focus - ${payload.title}: ${reason} (confidence ${confidenceLabel}).`);
    onSelectCitationFocus?.({
      sourceName: `Verifier - ${payload.title}`,
      extract: reason,
      graphNodeIds: [payload.nodeId],
      sceneRefs: payload.sceneRefs,
      eventRefs: payload.eventRefs,
    });
  };

  return (
    <div className="flex min-h-0 flex-col overflow-hidden border-l border-black/[0.06] bg-white/80 backdrop-blur-xl" style={{ width: `${Math.round(width)}px` }}>
      <div className="border-b border-black/[0.06] px-5 py-4">
        <h3 className="text-[15px] tracking-tight text-[#1d1d1f]">Information panel</h3>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5">
        <section className="space-y-2 rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
          <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">AI Work Graph</p>
          {hasWorkGraphPayload ? (
            <div>
              <WorkGraphViewer
                viewerHeight={viewerHeights.mindmap}
                onAskNode={onAskMindmapNode}
                onInspectEvidence={inspectWorkGraphEvidence}
                onInspectVerifier={inspectWorkGraphVerifier}
              />
              {renderViewerResizeHandle("mindmap", "mindmap")}
            </div>
          ) : hasMindmapPayload ? (
            <div>
              <MindmapViewer
                payload={workspaceGraphPayload as Record<string, unknown>}
                conversationId={selectedConversationId}
                viewerHeight={viewerHeights.mindmap}
                onAskNode={onAskMindmapNode}
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
              {workGraphSlice.error ? `Work graph unavailable: ${workGraphSlice.error}` : "Work graph is not available for this answer."}
            </div>
          )}
        </section>

        <section className="space-y-3">
          <VerificationSourceBar sources={sources} selectedSourceId={selectedSource?.id || ""} onSelectSource={selectSource} />
          <VerificationTabBar
            activeTab={memory.verificationTab}
            onChangeTab={setVerificationTab}
            evidenceMode={memory.evidenceMode}
            onChangeEvidenceMode={setEvidenceMode}
            searchQuery={searchQuery}
            onChangeSearchQuery={setSearchQuery}
          />

          {memory.verificationTab === "sources" ? (
            <VerificationSourceList sources={sources} selectedSourceId={selectedSource?.id || ""} onSelectSource={selectSource} />
          ) : null}

          {memory.verificationTab === "review" ? (
            activeCitation ? (
              <CitationPreviewPanel
                citationFocus={activeCitation}
                citationOpenUrl={citationOpenState.citationOpenUrl}
                citationRawUrl={citationOpenState.citationRawUrl}
                citationUsesWebsite={citationOpenState.citationUsesWebsite}
                citationWebsiteUrl={citationOpenState.citationWebsiteUrl}
                citationIsPdf={citationOpenState.citationIsPdf}
                citationIsImage={citationOpenState.citationIsImage}
                citationViewerHeight={viewerHeights.citation}
                evidenceMode={memory.evidenceMode}
                sourceEvidence={sourceEvidence}
                hasPreviousEvidence={activeEvidenceIndex > 0}
                hasNextEvidence={activeEvidenceIndex >= 0 && activeEvidenceIndex < evidenceRows.length - 1}
                onPreviousEvidence={() => jumpToNeighborEvidence(-1)}
                onNextEvidence={() => jumpToNeighborEvidence(1)}
                onSelectEvidence={selectEvidence}
                pdfZoom={pdfZoom}
                onPdfZoomChange={(next) => {
                  setPdfZoom(next);
                  updateMemory({ reviewZoom: next });
                }}
                onClear={onClearCitationFocus}
                renderResizeHandle={() => renderViewerResizeHandle("citation", "citation")}
              />
            ) : (
              <div className="rounded-xl border border-black/[0.06] bg-white p-3 text-[12px] text-[#6e6e73]">
                Choose a source or citation to start review.
              </div>
            )
          ) : null}

          {memory.verificationTab === "evidence" ? (
            <div className="rounded-2xl border border-[#d2d2d7] bg-gradient-to-b from-white to-[#f6f7fa] p-3 shadow-sm">
              <div className="mb-2 flex items-center justify-between gap-2">
                <p className="text-[10px] uppercase tracking-wide text-[#8e8e93]">Evidence</p>
                <p className="text-[11px] text-[#6e6e73]">{evidenceRows.length} snippets</p>
              </div>
              <EvidenceCardsList
                cards={evidenceRows}
                selectedEvidenceId={activeEvidenceId}
                evidenceMode={memory.evidenceMode}
                onSelectCard={selectEvidence}
              />
            </div>
          ) : null}

          {memory.verificationTab === "trail" ? (
            <VerificationTrailPanel cards={evidenceRows.length ? evidenceRows : evidenceCards} onSelectCard={selectEvidence} />
          ) : null}

          {memory.verificationTab === "compare" ? (
            <VerificationComparePanel cards={evidenceRows.length ? evidenceRows : evidenceCards} onSelectCard={selectEvidence} />
          ) : null}

          <VerificationFooter quality={qualitySummary} sourceCount={sources.length} evidenceCount={evidenceRows.length || evidenceCards.length} />
        </section>
      </div>
    </div>
  );
}
